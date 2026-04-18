from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from .actions import CommandRunner
from .classifier import EventClassifier
from .config import (
    AppConfig,
    build_selection_catalog,
    default_config_path,
    load_config,
    load_tasks,
)
from .constants import (
    IDLE_ICON,
    PANEL_KIND_CLASSIFIED,
    PANEL_KIND_DISCONNECTED,
    PANEL_KIND_PAUSED,
    PANEL_KIND_UNCLASSIFIED,
    UNKNOWN_PATH,
)
from .debug import DebugLogger, debug_enabled
from .dbus_service import DaemonDBusService
from .llm import OpenAICompatibleClient
from .models import (
    AppPaths,
    ClassificationResult,
    DisplayRow,
    PanelStateRecord,
    ProviderSnapshot,
    RefreshResult,
    SelectionCatalog,
    SpanRecord,
    ToolCall,
    UIStateRecord,
    utcnow,
)
from .providers import GnomeProvider
from .storage import (
    append_jsonl,
    ensure_state_dir,
    load_spans,
    load_status,
    load_tracking,
    save_span,
    save_tracking,
    save_ui_state,
)


@dataclass(slots=True)
class RuntimeState:
    catalog: SelectionCatalog
    catalog_hash: str
    panel_state: PanelStateRecord
    last_classified_started_at: datetime | None
    last_snapshot: ProviderSnapshot | None
    tracking_enabled: bool


class ActivityDaemon:
    def __init__(
        self, config: AppConfig, *, config_path: str | Path | None = None
    ) -> None:
        self.config = config
        self.config_path = (
            Path(config_path).expanduser() if config_path else default_config_path()
        )
        self.paths = AppPaths.from_state_dir(config.state_dir)
        ensure_state_dir(self.paths)
        self.debug = DebugLogger(self.paths.debug_log, enabled=debug_enabled())
        self.client = OpenAICompatibleClient(self.debug)
        self.classifier = EventClassifier(self.client, self.debug)
        self.command_runner = CommandRunner(self.debug)
        self.provider = GnomeProvider()
        self.decision_cache: dict[str, ClassificationResult] = {}
        self.runtime = self._load_runtime_state()
        self._refresh_lock = asyncio.Lock()
        self.dbus_service = DaemonDBusService(
            self.reload_config,
            self.set_tracking,
            self.runtime.panel_state,
            self._build_ui_state(),
            self.runtime.tracking_enabled,
        )

    def _load_runtime_state(self) -> RuntimeState:
        catalog = build_selection_catalog(self.config, load_tasks())
        catalog_hash = catalog.fingerprint()
        panel_state = load_status(self.paths.status_json)
        if panel_state is None:
            panel_state = PanelStateRecord.disconnected(
                revision=0,
                published_at=utcnow(),
                catalog_hash=catalog_hash,
            )
        else:
            panel_state = panel_state.model_copy(update={"catalog_hash": catalog_hash})
        last_classified_started_at = (
            panel_state.published_at
            if panel_state.kind == PANEL_KIND_CLASSIFIED
            else None
        )
        return RuntimeState(
            catalog=catalog,
            catalog_hash=catalog_hash,
            panel_state=panel_state,
            last_classified_started_at=last_classified_started_at,
            last_snapshot=None,
            tracking_enabled=load_tracking(self.paths.tracking_json),
        )

    async def reload_config(self) -> RefreshResult:
        async with self._refresh_lock:
            previous_paths = self.runtime.catalog.allowed_paths()
            self.debug.log("config_reload_start", catalog=sorted(previous_paths))
            try:
                config = load_config(self.config_path)
                catalog = build_selection_catalog(config, load_tasks())
            except Exception as exc:
                self.debug.log("config_reload_failed", error=str(exc))
                return RefreshResult(
                    success=False,
                    message=f"Reload failed ({exc}), keeping current catalog",
                    used_cached=True,
                )

            self.config = config
            self.runtime.catalog = catalog
            self.runtime.catalog_hash = catalog.fingerprint()
            self.decision_cache.clear()
            message = describe_catalog_reload(
                previous_paths,
                catalog.allowed_paths(),
                self.runtime.catalog_hash,
            )
            self.debug.log(
                "config_reload_complete",
                catalog_hash=self.runtime.catalog_hash,
                catalog=sorted(catalog.allowed_paths()),
            )
            await self._reconcile_panel_state_after_reload()
            self._publish_ui_state()
            return RefreshResult(success=True, message=message, used_cached=False)

    async def set_tracking(self, enabled: bool) -> None:
        if self.runtime.tracking_enabled == enabled:
            return
        self.runtime.tracking_enabled = enabled
        save_tracking(self.paths.tracking_json, enabled)
        self.dbus_service.update_tracking_state(enabled)
        self.debug.log("tracking_state_changed", enabled=enabled)
        if not enabled:
            await self._publish_paused()
        else:
            await self._publish_disconnected(reason="tracking_resumed")

    async def run(self) -> None:
        await self.dbus_service.start()
        self._publish_ui_state()
        if self.runtime.tracking_enabled:
            await self._publish_disconnected(reason="startup")
        else:
            await self._publish_paused()
        await self._provider_loop()

    async def _provider_loop(self) -> None:
        while True:
            try:
                await self.provider.monitor(self.handle_snapshot)
            except Exception as exc:
                self.debug.log("provider_disconnected", error=str(exc))
                await self._publish_disconnected(reason=str(exc))
                await asyncio.sleep(1)

    async def handle_snapshot(self, snapshot: ProviderSnapshot) -> None:
        if not self.runtime.tracking_enabled:
            return
        self.runtime.last_snapshot = snapshot
        self._log_raw_event(snapshot)
        state = snapshot.state
        previous_result = self._current_result()
        cache_key = self._decision_key(snapshot, previous_result)
        result = self.decision_cache.get(cache_key)
        self.debug.log(
            "provider_state",
            previous_result=previous_result.model_dump(mode="json")
            if previous_result is not None
            else None,
            cache_key=cache_key,
            revision=snapshot.revision,
            state=state.model_dump(mode="json", exclude_none=True),
        )
        if result is None:
            result = await self.classifier.classify(
                self.config,
                state,
                self.runtime.catalog,
                previous_result,
            )
            self.decision_cache[cache_key] = result
            self.debug.log(
                "classifier_cache_store",
                cache_key=cache_key,
                selected=result.model_dump(mode="json"),
            )
        else:
            self.debug.log(
                "classifier_cache_hit",
                cache_key=cache_key,
                selected=result.model_dump(mode="json"),
            )

        if self._same_result(previous_result, result):
            self.debug.log("activity_unchanged", selected=result.model_dump(mode="json"))
            return

        if result.activity_path == UNKNOWN_PATH:
            await self._publish_unclassified(state)
            return
        if result.activity_path == "idle":
            await self._publish_idle(state)
            return

        await self._publish_classified(result, state)

    async def _publish_classified(
        self, result: ClassificationResult, state: Any
    ) -> None:
        previous_result = self._current_result()
        now = utcnow()
        await self._close_previous_span(now)
        await self._run_actions_for_result(result, previous_result)
        activity_entry = self.runtime.catalog.entry_for_path(result.activity_path)
        top_level = result.activity_path.split("/", 1)[0]
        panel_state = PanelStateRecord.classified(
            revision=self.runtime.panel_state.revision + 1,
            path=result.activity_path,
            task_path=result.task_path,
            top_level_id=top_level,
            top_level_label=top_level,
            icon_name=activity_entry.icon or "applications-system-symbolic",
            published_at=now,
            catalog_hash=self.runtime.catalog_hash,
        )
        self.runtime.last_classified_started_at = now
        await self._commit_panel_state(
            panel_state,
            state=state,
            previous=previous_result,
        )

    async def _publish_idle(self, state: Any) -> None:
        previous_result = self._current_result()
        now = utcnow()
        await self._close_previous_span(now)
        await self._run_actions_for_result(
            ClassificationResult(activity_path="idle", task_path=None),
            previous_result,
        )
        panel_state = PanelStateRecord.classified(
            revision=self.runtime.panel_state.revision + 1,
            path="idle",
            task_path=None,
            top_level_id="idle",
            top_level_label="idle",
            icon_name=IDLE_ICON,
            published_at=now,
            catalog_hash=self.runtime.catalog_hash,
        )
        self.runtime.last_classified_started_at = now
        await self._commit_panel_state(
            panel_state,
            state=state,
            previous=previous_result,
            reason="idle",
        )

    async def _publish_unclassified(
        self, state: Any, *, reason: str | None = None
    ) -> None:
        previous_result = self._current_result()
        now = utcnow()
        await self._close_previous_span(now)
        await self._run_actions_for_result(
            ClassificationResult(activity_path=UNKNOWN_PATH, task_path=None),
            previous_result,
        )
        self.runtime.last_classified_started_at = None
        panel_state = PanelStateRecord.unclassified(
            revision=self.runtime.panel_state.revision + 1,
            published_at=now,
            catalog_hash=self.runtime.catalog_hash,
        )
        await self._commit_panel_state(
            panel_state,
            state=state,
            previous=previous_result,
            reason=reason,
        )

    async def _publish_disconnected(self, *, reason: str | None = None) -> None:
        previous_result = self._current_result()
        now = utcnow()
        await self._close_previous_span(now)
        await self._run_actions_for_result(
            ClassificationResult(activity_path=UNKNOWN_PATH, task_path=None),
            previous_result,
        )
        self.runtime.last_classified_started_at = None
        panel_state = PanelStateRecord.disconnected(
            revision=self.runtime.panel_state.revision + 1,
            published_at=now,
            catalog_hash=self.runtime.catalog_hash,
        )
        await self._commit_panel_state(
            panel_state,
            previous=previous_result,
            reason=reason,
        )

    async def _publish_paused(self) -> None:
        previous_result = self._current_result()
        now = utcnow()
        await self._close_previous_span(now)
        await self._run_actions_for_result(
            ClassificationResult(activity_path=UNKNOWN_PATH, task_path=None),
            previous_result,
        )
        self.runtime.last_classified_started_at = None
        panel_state = PanelStateRecord.paused(
            revision=self.runtime.panel_state.revision + 1,
            published_at=now,
            catalog_hash=self.runtime.catalog_hash,
        )
        await self._commit_panel_state(
            panel_state,
            previous=previous_result,
            reason="tracking_paused",
        )

    async def _commit_panel_state(
        self,
        panel_state: PanelStateRecord,
        *,
        state: Any = None,
        previous: ClassificationResult | None,
        reason: str | None = None,
    ) -> None:
        if panel_state.same_value(self.runtime.panel_state):
            return
        self.runtime.panel_state = panel_state
        ui_state = self._build_ui_state()
        save_ui_state(self.paths.status_json, ui_state)
        self.dbus_service.update_panel_state(panel_state)
        self.dbus_service.update_ui_state(ui_state)
        self.debug.log(
            "activity_changed",
            previous_result=previous.model_dump(mode="json")
            if previous is not None
            else None,
            selected=self._current_result().model_dump(mode="json")
            if self._current_result() is not None
            else None,
            kind=panel_state.kind,
            catalog_hash=panel_state.catalog_hash,
            reason=reason,
        )
        append_jsonl(
            self.paths.activity_log,
            {
                "ts": panel_state.published_at.isoformat(),
                "event": "activity_change",
                "kind": panel_state.kind,
                "activity_path": panel_state.path,
                "task_path": panel_state.task_path,
                "top_level": panel_state.top_level_id,
                "catalog_hash": panel_state.catalog_hash,
                "title": state.focused_window.title
                if state and state.focused_window
                else "",
                "wm_class": state.focused_window.wm_class
                if state and state.focused_window
                else "",
                "reason": reason,
            },
        )

    def _publish_ui_state(self) -> None:
        ui_state = self._build_ui_state()
        save_ui_state(self.paths.status_json, ui_state)
        self.dbus_service.update_ui_state(ui_state)

    def _build_ui_state(self) -> UIStateRecord:
        return UIStateRecord.from_panel_state(
            self.runtime.panel_state,
            tracking_enabled=self.runtime.tracking_enabled,
            display_label=self._display_label_for_state(),
            display_rows=self._build_display_rows(),
        )

    def _display_label_for_state(self) -> str:
        current = self.runtime.panel_state
        if current.kind == PANEL_KIND_CLASSIFIED and current.path:
            if current.task_path:
                return f"{current.path} • {current.task_path}"
            return current.path
        if current.kind == PANEL_KIND_UNCLASSIFIED:
            return UNKNOWN_PATH
        if current.kind == PANEL_KIND_PAUSED:
            return PANEL_KIND_PAUSED
        return PANEL_KIND_DISCONNECTED

    def _build_display_rows(self) -> list[DisplayRow]:
        durations = self._today_duration_by_path()
        current_activity = self.runtime.panel_state.path
        current_task = self.runtime.panel_state.task_path
        rows: list[DisplayRow] = []

        for entry in self.runtime.catalog.activity_entries + self.runtime.catalog.task_entries:
            seconds = durations.pop(entry.path, 0.0)
            rows.append(
                DisplayRow(
                    path=entry.path,
                    label=entry.path,
                    icon_name=entry.icon,
                    seconds=seconds,
                    is_selected=entry.path in {current_activity, current_task},
                    is_legacy=False,
                )
            )

        for path in sorted(durations, key=lambda item: (-durations[item], item)):
            rows.append(
                DisplayRow(
                    path=path,
                    label=path,
                    icon_name="applications-system-symbolic",
                    seconds=durations[path],
                    is_selected=path in {current_activity, current_task},
                    is_legacy=True,
                )
            )
        return rows

    def _today_duration_by_path(self) -> dict[str, float]:
        spans = load_spans(self.paths.spans_log)
        day_start = datetime.now(tz=UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        totals: dict[str, float] = {}
        for span in spans:
            if span.ended_at < day_start:
                continue
            totals[span.path] = totals.get(span.path, 0.0) + span.duration_seconds
            if span.task_path:
                totals[span.task_path] = totals.get(span.task_path, 0.0) + span.duration_seconds
        return totals

    async def _reconcile_panel_state_after_reload(self) -> None:
        current = self.runtime.panel_state
        if current.kind != PANEL_KIND_CLASSIFIED or current.path is None:
            return
        allowed = self.runtime.catalog.allowed_paths()
        if current.path != "idle" and current.path not in allowed:
            await self._publish_unclassified(state=None, reason="path_removed_from_catalog")
            return
        if current.task_path and current.task_path not in allowed:
            self.runtime.panel_state = current.model_copy(
                update={"task_path": None, "catalog_hash": self.runtime.catalog_hash}
            )
            self.dbus_service.update_panel_state(self.runtime.panel_state)
            return
        self.runtime.panel_state = current.model_copy(
            update={"catalog_hash": self.runtime.catalog_hash}
        )
        self.dbus_service.update_panel_state(self.runtime.panel_state)

    def _log_raw_event(self, snapshot: ProviderSnapshot) -> None:
        window = snapshot.state.focused_window
        append_jsonl(
            self.paths.raw_events_log,
            {
                "ts": snapshot.state.timestamp.isoformat(),
                "event": "window_change",
                "revision": snapshot.revision,
                "screen_locked": snapshot.state.screen_locked,
                "title": window.title if window else "",
                "wm_class": window.wm_class if window else "",
                "app_id": window.app_id if window else None,
                "workspace": window.workspace if window else None,
                "workspace_name": window.workspace_name if window else None,
                "active_workspace_name": snapshot.state.active_workspace_name,
                "urgent": window.urgent if window else False,
                "demands_attention": window.demands_attention if window else False,
                "z_order": window.z_order if window else None,
                "idle_time_seconds": snapshot.state.idle_time_seconds,
            },
        )

    def _decision_key(
        self, snapshot: ProviderSnapshot, previous_result: ClassificationResult | None
    ) -> str:
        window = snapshot.state.focused_window
        normalized = {
            "title": window.title if window else "",
            "wm_class": window.wm_class if window else "",
            "wm_class_instance": window.wm_class_instance if window else None,
            "workspace_name": window.workspace_name if window else None,
            "active_workspace_name": snapshot.state.active_workspace_name,
            "fullscreen": window.fullscreen if window else False,
            "maximized": window.maximized if window else False,
            "open_windows": [
                {
                    "title": open_window.title,
                    "wm_class": open_window.wm_class,
                    "wm_class_instance": open_window.wm_class_instance,
                    "app_id": open_window.app_id,
                    "workspace": open_window.workspace,
                    "workspace_name": open_window.workspace_name,
                    "z_order": open_window.z_order,
                }
                for open_window in sorted(
                    snapshot.state.open_windows,
                    key=lambda item: (
                        item.z_order is None,
                        item.z_order if item.z_order is not None else 9999,
                        item.wm_class,
                        item.title,
                    ),
                )
                if open_window.title or open_window.wm_class
            ],
            "screen_locked": snapshot.state.screen_locked,
            "idle_time_seconds": snapshot.state.idle_time_seconds,
            "previous_result": previous_result.model_dump(mode="json")
            if previous_result is not None
            else None,
            "catalog_hash": self.runtime.catalog_hash,
        }
        serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def _run_actions_for_result(
        self,
        result: ClassificationResult,
        previous_result: ClassificationResult | None,
    ) -> None:
        current_path = result.task_path or result.activity_path
        previous_path = (
            previous_result.task_path or previous_result.activity_path
            if previous_result is not None
            else None
        )
        if current_path == previous_path or current_path == "idle":
            return
        await self._run_actions(current_path)

    async def _run_actions(self, path: str) -> None:
        calls = self._calls_for_path(path)
        if not calls:
            return
        self.debug.log(
            "action_dispatch",
            path=path,
            calls=[call.model_dump(mode="json") for call in calls],
        )
        await self.command_runner.run_calls(self.config.tools.actions, calls)

    def _calls_for_path(self, path: str) -> list[ToolCall]:
        if path not in self.runtime.catalog.allowed_paths():
            return []
        return self.runtime.catalog.actions_for_path(path)

    async def _close_previous_span(self, ended_at: datetime) -> None:
        if self.runtime.panel_state.kind != PANEL_KIND_CLASSIFIED:
            return
        if (
            self.runtime.panel_state.path is None
            or self.runtime.last_classified_started_at is None
        ):
            return
        span = SpanRecord(
            path=self.runtime.panel_state.path,
            top_level=self.runtime.panel_state.top_level_id
            or self.runtime.panel_state.path.split("/", 1)[0],
            task_path=self.runtime.panel_state.task_path,
            started_at=self.runtime.last_classified_started_at,
            ended_at=ended_at,
            duration_seconds=max(
                0.0,
                (ended_at - self.runtime.last_classified_started_at).total_seconds(),
            ),
        )
        save_span(self.paths.spans_log, span)

    def _current_result(self) -> ClassificationResult | None:
        current = self.runtime.panel_state
        if current.kind == PANEL_KIND_CLASSIFIED and current.path:
            return ClassificationResult(
                activity_path=current.path,
                task_path=current.task_path,
            )
        if current.kind == PANEL_KIND_UNCLASSIFIED:
            return ClassificationResult(activity_path=UNKNOWN_PATH, task_path=None)
        return None

    def _same_result(
        self,
        left: ClassificationResult | None,
        right: ClassificationResult | None,
    ) -> bool:
        if left is None or right is None:
            return left is right
        return left == right

    async def status_payload(self) -> dict[str, Any]:
        return self._build_ui_state().model_dump(mode="json")


def describe_catalog_reload(
    previous_paths: set[str],
    current_paths: set[str],
    catalog_hash: str,
) -> str:
    added = sorted(current_paths - previous_paths)
    removed = sorted(previous_paths - current_paths)
    message = f"Loaded {len(current_paths)} catalog entries"
    if not added and not removed:
        return f"{message} (unchanged, hash={catalog_hash[:8]})"

    parts = [f"hash={catalog_hash[:8]}"]
    if added:
        parts.append("added: " + summarize_paths(added))
    if removed:
        parts.append("removed: " + summarize_paths(removed))
    return f"{message} ({'; '.join(parts)})"


def summarize_paths(paths: list[str], *, limit: int = 5) -> str:
    if not paths:
        return "none"
    if len(paths) <= limit:
        return ", ".join(paths)
    visible = ", ".join(paths[:limit])
    return f"{visible}, +{len(paths) - limit} more"
