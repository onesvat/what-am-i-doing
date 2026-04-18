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
from .config import AppConfig, default_config_path, load_config
from .constants import (
    IDLE_ICON,
    PANEL_KIND_CLASSIFIED,
    PANEL_KIND_DISCONNECTED,
    PANEL_KIND_PAUSED,
    PANEL_KIND_UNCLASSIFIED,
    UNKNOWN_CHOICE_PATH,
)
from .debug import DebugLogger, debug_enabled
from .dbus_service import DaemonDBusService
from .llm import OpenAICompatibleClient
from .models import (
    AppPaths,
    ChoiceRegistry,
    DisplayRow,
    PanelStateRecord,
    ProviderSnapshot,
    RefreshResult,
    SpanRecord,
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
    choices: ChoiceRegistry
    choices_hash: str
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
        self.decision_cache: dict[str, str] = {}
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
        choices = self.config.choice_registry()
        choices_hash = choices.fingerprint()
        panel_state = load_status(self.paths.status_json)
        if panel_state is None:
            panel_state = PanelStateRecord.disconnected(
                revision=0,
                published_at=utcnow(),
                choices_hash=choices_hash,
            )
        else:
            panel_state = panel_state.model_copy(update={"choices_hash": choices_hash})
        last_classified_started_at = (
            panel_state.published_at
            if panel_state.kind == PANEL_KIND_CLASSIFIED
            else None
        )
        tracking_enabled = load_tracking(self.paths.tracking_json)
        return RuntimeState(
            choices=choices,
            choices_hash=choices_hash,
            panel_state=panel_state,
            last_classified_started_at=last_classified_started_at,
            last_snapshot=None,
            tracking_enabled=tracking_enabled,
        )

    async def reload_config(self) -> RefreshResult:
        async with self._refresh_lock:
            previous_paths = self.runtime.choices.allowed_paths()
            self.debug.log(
                "config_reload_start",
                choices=sorted(previous_paths),
            )
            try:
                config = load_config(self.config_path)
                choices = config.choice_registry()
            except Exception as exc:
                self.debug.log("config_reload_failed", error=str(exc))
                return RefreshResult(
                    success=False,
                    message=f"Reload failed ({exc}), keeping current choices",
                    used_cached=True,
                )

            self.config = config
            self.runtime.choices = choices
            self.runtime.choices_hash = choices.fingerprint()
            self.decision_cache.clear()
            message = describe_choice_reload(
                previous_paths,
                choices.allowed_paths(),
                self.runtime.choices_hash,
            )
            self.debug.log(
                "config_reload_complete",
                choices_hash=self.runtime.choices_hash,
                choices=sorted(choices.allowed_paths()),
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
        state = snapshot.state
        self._log_raw_event(snapshot)
        previous_selection = self._previous_selection()
        cache_key = self._decision_key(snapshot, previous_selection)
        selected = self.decision_cache.get(cache_key)
        self.debug.log(
            "provider_state",
            previous_path=previous_selection,
            cache_key=cache_key,
            revision=snapshot.revision,
            state=state.model_dump(mode="json", exclude_none=True),
        )
        if selected is None:
            selected = await self.classifier.classify(
                self.config,
                state,
                self.runtime.choices,
                previous_selection,
            )
            self.decision_cache[cache_key] = selected
            self.debug.log(
                "classifier_cache_store", cache_key=cache_key, selected_path=selected
            )
        else:
            self.debug.log(
                "classifier_cache_hit", cache_key=cache_key, selected_path=selected
            )

        if self._current_selection() == selected:
            self.debug.log("activity_unchanged", selected_path=selected)
            return

        if selected == UNKNOWN_CHOICE_PATH:
            await self._publish_unclassified(state)
            return
        if selected == "idle":
            await self._publish_idle(state)
            return

        await self._publish_classified(selected, state)

    async def _publish_classified(self, path: str, state) -> None:
        previous = self._current_selection()
        now = utcnow()
        await self._close_previous_span(now)
        await self._run_actions(path)
        choice = self.runtime.choices.choice_for_path(path)
        top_level = path.split("/", 1)[0]
        panel_state = PanelStateRecord.classified(
            revision=self.runtime.panel_state.revision + 1,
            path=path,
            top_level_id=top_level,
            top_level_label=top_level,
            icon_name=choice.icon or "applications-system-symbolic",
            published_at=now,
            choices_hash=self.runtime.choices_hash,
        )
        self.runtime.last_classified_started_at = now
        await self._commit_panel_state(panel_state, state=state, previous=previous)

    async def _publish_idle(self, state) -> None:
        previous = self._current_selection()
        now = utcnow()
        await self._close_previous_span(now)
        panel_state = PanelStateRecord.classified(
            revision=self.runtime.panel_state.revision + 1,
            path="idle",
            top_level_id="idle",
            top_level_label="idle",
            icon_name=IDLE_ICON,
            published_at=now,
            choices_hash=self.runtime.choices_hash,
        )
        self.runtime.last_classified_started_at = now
        await self._commit_panel_state(
            panel_state,
            state=state,
            previous=previous,
            reason="idle",
        )

    async def _publish_unclassified(self, state, *, reason: str | None = None) -> None:
        previous = self._current_selection()
        now = utcnow()
        await self._close_previous_span(now)
        self.runtime.last_classified_started_at = None
        panel_state = PanelStateRecord.unclassified(
            revision=self.runtime.panel_state.revision + 1,
            published_at=now,
            choices_hash=self.runtime.choices_hash,
        )
        await self._commit_panel_state(
            panel_state, state=state, previous=previous, reason=reason
        )

    async def _publish_disconnected(self, *, reason: str | None = None) -> None:
        previous = self._current_selection()
        now = utcnow()
        await self._close_previous_span(now)
        self.runtime.last_classified_started_at = None
        panel_state = PanelStateRecord.disconnected(
            revision=self.runtime.panel_state.revision + 1,
            published_at=now,
            choices_hash=self.runtime.choices_hash,
        )
        await self._commit_panel_state(panel_state, previous=previous, reason=reason)

    async def _publish_paused(self) -> None:
        previous = self._current_selection()
        now = utcnow()
        await self._close_previous_span(now)
        self.runtime.last_classified_started_at = None
        panel_state = PanelStateRecord.paused(
            revision=self.runtime.panel_state.revision + 1,
            published_at=now,
            choices_hash=self.runtime.choices_hash,
        )
        await self._commit_panel_state(
            panel_state, previous=previous, reason="tracking_paused"
        )

    async def _commit_panel_state(
        self,
        panel_state: PanelStateRecord,
        *,
        state=None,
        previous: str | None,
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
            previous_path=previous,
            selected_path=self._current_selection(),
            kind=panel_state.kind,
            choices_hash=panel_state.choices_hash,
            reason=reason,
        )
        append_jsonl(
            self.paths.activity_log,
            {
                "ts": panel_state.published_at.isoformat(),
                "event": "activity_change",
                "kind": panel_state.kind,
                "path": panel_state.path,
                "top_level": panel_state.top_level_id,
                "choices_hash": panel_state.choices_hash,
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
            return current.path
        if current.kind == PANEL_KIND_UNCLASSIFIED:
            return UNKNOWN_CHOICE_PATH
        if current.kind == PANEL_KIND_PAUSED:
            return PANEL_KIND_PAUSED
        return PANEL_KIND_DISCONNECTED

    def _build_display_rows(self) -> list[DisplayRow]:
        durations = self._today_duration_by_path()
        current_path = self.runtime.panel_state.path
        rows: list[DisplayRow] = []

        for choice in self.runtime.choices.choices:
            seconds = durations.pop(choice.path, 0.0)
            rows.append(
                DisplayRow(
                    path=choice.path,
                    label=choice.path,
                    icon_name=choice.icon,
                    seconds=seconds,
                    is_selected=current_path == choice.path,
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
                    is_selected=current_path == path,
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
        return totals

    async def _reconcile_panel_state_after_reload(self) -> None:
        current = self.runtime.panel_state
        if current.kind != PANEL_KIND_CLASSIFIED or current.path is None:
            return
        if current.path == "idle" or current.path in self.runtime.choices.allowed_paths():
            self.runtime.panel_state = current.model_copy(
                update={"choices_hash": self.runtime.choices_hash}
            )
            self.dbus_service.update_panel_state(self.runtime.panel_state)
            return
        await self._publish_unclassified(
            state=None, reason="path_removed_from_choices"
        )

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
        self, snapshot: ProviderSnapshot, previous_selection: str | None
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
            "previous_selection": previous_selection,
            "choices_hash": self.runtime.choices_hash,
        }
        serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def _run_actions(self, path: str) -> None:
        calls = self.runtime.choices.actions_for_path(path)
        self.debug.log(
            "action_dispatch",
            path=path,
            calls=[call.model_dump(mode="json") for call in calls],
        )
        if not calls:
            return
        await self.command_runner.run_calls(self.config.tools.actions, calls)

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
            started_at=self.runtime.last_classified_started_at,
            ended_at=ended_at,
            duration_seconds=max(
                0.0,
                (ended_at - self.runtime.last_classified_started_at).total_seconds(),
            ),
        )
        save_span(self.paths.spans_log, span)

    def _current_selection(self) -> str | None:
        current = self.runtime.panel_state
        if current.kind == PANEL_KIND_CLASSIFIED:
            return current.path
        if current.kind == PANEL_KIND_UNCLASSIFIED:
            return UNKNOWN_CHOICE_PATH
        return None

    def _previous_selection(self) -> str | None:
        current = self.runtime.panel_state
        if current.kind == PANEL_KIND_CLASSIFIED:
            return current.path
        if current.kind == PANEL_KIND_UNCLASSIFIED:
            return UNKNOWN_CHOICE_PATH
        return None

    async def status_payload(self) -> dict[str, Any]:
        return self._build_ui_state().model_dump(mode="json")


def describe_choice_reload(
    previous_paths: set[str],
    current_paths: set[str],
    choices_hash: str,
) -> str:
    added = sorted(current_paths - previous_paths)
    removed = sorted(previous_paths - current_paths)
    message = f"Loaded {len(current_paths)} choices"
    if not added and not removed:
        return f"{message} (unchanged, hash={choices_hash[:8]})"

    parts = [f"hash={choices_hash[:8]}"]
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
