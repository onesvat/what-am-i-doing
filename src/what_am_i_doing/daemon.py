from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any

from .actions import CommandRunner
from .classifier import EventClassifier
from .config import AppConfig
from .constants import (
    PANEL_KIND_CLASSIFIED,
    PANEL_KIND_DISCONNECTED,
    PANEL_KIND_UNCLASSIFIED,
)
from .debug import DebugLogger, debug_enabled
from .dbus_service import DaemonDBusService
from .generator import TaxonomyGenerator
from .llm import OpenAICompatibleClient
from .models import (
    AppPaths,
    PanelStateRecord,
    ProviderSnapshot,
    RefreshResult,
    SpanRecord,
    Taxonomy,
    utcnow,
)
from .providers import GnomeProvider
from .storage import (
    append_jsonl,
    ensure_state_dir,
    load_status,
    load_taxonomy,
    save_span,
    save_status,
    save_taxonomy,
)


@dataclass(slots=True)
class RuntimeState:
    taxonomy: Taxonomy
    taxonomy_hash: str
    panel_state: PanelStateRecord
    last_classified_started_at: datetime | None
    last_snapshot: ProviderSnapshot | None


class ActivityDaemon:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.paths = AppPaths.from_state_dir(config.state_dir)
        ensure_state_dir(self.paths)
        self.debug = DebugLogger(self.paths.debug_log, enabled=debug_enabled())
        self.client = OpenAICompatibleClient(self.debug)
        self.generator = TaxonomyGenerator(self.client, self.debug)
        self.classifier = EventClassifier(self.client, self.debug)
        self.command_runner = CommandRunner(self.debug)
        self.provider = GnomeProvider()
        self.decision_cache: dict[str, str] = {}
        self.runtime = self._load_runtime_state()
        self._refresh_lock = asyncio.Lock()
        self.dbus_service = DaemonDBusService(
            self.refresh_taxonomy, self.runtime.panel_state
        )

    def _load_runtime_state(self) -> RuntimeState:
        taxonomy = self.config.normalize_generated_taxonomy(
            load_taxonomy(self.paths.taxonomy_json) or self.config.seed_taxonomy()
        )
        taxonomy_hash = taxonomy.fingerprint()
        panel_state = load_status(self.paths.status_json)
        if panel_state is None:
            panel_state = PanelStateRecord.disconnected(
                revision=0, published_at=utcnow()
            )
        last_classified_started_at = (
            panel_state.published_at
            if panel_state.kind == PANEL_KIND_CLASSIFIED
            else None
        )
        return RuntimeState(
            taxonomy=taxonomy,
            taxonomy_hash=taxonomy_hash,
            panel_state=panel_state,
            last_classified_started_at=last_classified_started_at,
            last_snapshot=None,
        )

    async def refresh_taxonomy(self) -> RefreshResult:
        async with self._refresh_lock:
            context_outputs: dict[str, str] = {}
            for name, tool in self.config.tools.context.items():
                try:
                    result = await self.command_runner.run(tool, [])
                except Exception as exc:
                    context_outputs[name] = "<unavailable>"
                    self.debug.log(
                        "context_tool_unavailable",
                        tool_name=name,
                        error=str(exc),
                    )
                    continue
                context_outputs[name] = self._context_output_for_prompt(result)
            self.debug.log("taxonomy_refresh_start", context_outputs=context_outputs)
            try:
                taxonomy = await self.generator.generate(self.config, context_outputs)
                message = f"Generated {len(taxonomy.allowed_paths())} categories"
                result = RefreshResult(success=True, message=message, used_cached=False)
            except Exception as exc:
                self.debug.log("taxonomy_refresh_failed", error=str(exc))
                taxonomy = self.config.normalize_generated_taxonomy(
                    load_taxonomy(self.paths.taxonomy_json)
                    or self.config.seed_taxonomy()
                )
                message = f"Generator failed ({exc}), using cached taxonomy"
                result = RefreshResult(success=False, message=message, used_cached=True)
            self.runtime.taxonomy = taxonomy
            self.runtime.taxonomy_hash = taxonomy.fingerprint()
            save_taxonomy(self.paths.taxonomy_json, taxonomy)
            self.debug.log(
                "taxonomy_refresh_complete",
                taxonomy_hash=self.runtime.taxonomy_hash,
                categories=sorted(taxonomy.allowed_paths()),
            )
            await self._reconcile_panel_state_after_taxonomy_refresh()
            return result

    async def run(self) -> None:
        await self.dbus_service.start()
        await self.refresh_taxonomy()
        await self._publish_disconnected(reason="startup")
        await asyncio.gather(self._refresh_loop(), self._provider_loop())

    async def _refresh_loop(self) -> None:
        if self.config.generator.interval_minutes == -1:
            return
        while True:
            await asyncio.sleep(self.config.generator.interval_minutes * 60)
            await self.refresh_taxonomy()

    async def _provider_loop(self) -> None:
        while True:
            try:
                await self.provider.monitor(self.handle_snapshot)
            except Exception as exc:
                self.debug.log("provider_disconnected", error=str(exc))
                await self._publish_disconnected(reason=str(exc))
                await asyncio.sleep(1)

    async def handle_snapshot(self, snapshot: ProviderSnapshot) -> None:
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
                self.runtime.taxonomy,
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

        if (
            self._current_selection() == selected
            and self.runtime.panel_state.kind != PANEL_KIND_DISCONNECTED
        ):
            self.debug.log("activity_unchanged", selected_path=selected)
            return

        if selected == PANEL_KIND_UNCLASSIFIED:
            await self._publish_unclassified(state)
            return

        await self._publish_classified(selected, state)

    async def _publish_classified(self, path: str, state) -> None:
        previous = self._current_selection()
        now = utcnow()
        await self._close_previous_span(now)
        await self._run_actions(path)
        top_node, _ = self.runtime.taxonomy.node_for_path(path)
        panel_state = PanelStateRecord.classified(
            revision=self.runtime.panel_state.revision + 1,
            path=path,
            top_level_id=path.split("/", 1)[0],
            top_level_label=path.split("/", 1)[0],
            icon_name=top_node.icon or "applications-system-symbolic",
            published_at=now,
            taxonomy_hash=self.runtime.taxonomy_hash,
        )
        self.runtime.last_classified_started_at = now
        await self._commit_panel_state(panel_state, state=state, previous=previous)

    async def _publish_unclassified(self, state, *, reason: str | None = None) -> None:
        previous = self._current_selection()
        now = utcnow()
        await self._close_previous_span(now)
        self.runtime.last_classified_started_at = None
        panel_state = PanelStateRecord.unclassified(
            revision=self.runtime.panel_state.revision + 1,
            published_at=now,
            taxonomy_hash=self.runtime.taxonomy_hash,
        )
        await self._commit_panel_state(
            panel_state, state=state, previous=previous, reason=reason
        )

    async def _publish_disconnected(self, *, reason: str | None = None) -> None:
        if self.runtime.panel_state.kind == PANEL_KIND_DISCONNECTED:
            return
        previous = self._current_selection()
        now = utcnow()
        await self._close_previous_span(now)
        self.runtime.last_classified_started_at = None
        panel_state = PanelStateRecord.disconnected(
            revision=self.runtime.panel_state.revision + 1,
            published_at=now,
        )
        await self._commit_panel_state(panel_state, previous=previous, reason=reason)

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
        save_status(self.paths.status_json, panel_state)
        self.dbus_service.update_panel_state(panel_state)
        self.debug.log(
            "activity_changed",
            previous_path=previous,
            selected_path=self._current_selection(),
            kind=panel_state.kind,
            taxonomy_hash=panel_state.taxonomy_hash,
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
                "taxonomy_hash": panel_state.taxonomy_hash,
                "title": state.focused_window.title
                if state and state.focused_window
                else "",
                "wm_class": state.focused_window.wm_class
                if state and state.focused_window
                else "",
                "reason": reason,
            },
        )

    async def _reconcile_panel_state_after_taxonomy_refresh(self) -> None:
        current = self.runtime.panel_state
        if current.kind != PANEL_KIND_CLASSIFIED or current.path is None:
            return
        if current.path in self.runtime.taxonomy.allowed_paths():
            return
        await self._publish_unclassified(
            state=None, reason="path_removed_from_taxonomy"
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
            "taxonomy_hash": self.runtime.taxonomy_hash,
        }
        serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _context_output_for_prompt(self, result) -> str:
        if result.returncode != 0:
            return "<unavailable>"
        stdout = result.stdout.strip()
        if stdout:
            return stdout
        return "<empty>"

    async def _run_actions(self, path: str) -> None:
        calls = self.runtime.taxonomy.tools_for_path(path)
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
            return PANEL_KIND_UNCLASSIFIED
        return None

    def _previous_selection(self) -> str | None:
        current = self.runtime.panel_state
        if current.kind == PANEL_KIND_CLASSIFIED:
            return current.path
        if current.kind == PANEL_KIND_UNCLASSIFIED:
            return PANEL_KIND_UNCLASSIFIED
        return None

    async def status_payload(self) -> dict[str, Any]:
        return {
            **self.runtime.panel_state.payload(),
            "revision": self.runtime.panel_state.revision,
        }
