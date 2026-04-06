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
from .debug import DebugLogger, debug_enabled
from .dbus_service import DaemonDBusService
from .generator import TaxonomyGenerator
from .llm import OpenAICompatibleClient
from .models import AppPaths, ProviderState, SpanRecord, StatusRecord, Taxonomy, utcnow
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
    status: StatusRecord | None
    last_changed_at: datetime | None


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
        self.dbus_service = DaemonDBusService(self.refresh_taxonomy)

    def _load_runtime_state(self) -> RuntimeState:
        taxonomy = load_taxonomy(self.paths.taxonomy_json) or self.config.seed_taxonomy()
        taxonomy = taxonomy.ensure_fallback(self.config.fallback_category)
        status = load_status(self.paths.status_json)
        last_changed_at = status.updated_at if status is not None else None
        return RuntimeState(
            taxonomy=taxonomy,
            taxonomy_hash=taxonomy.fingerprint(),
            status=status,
            last_changed_at=last_changed_at,
        )

    async def refresh_taxonomy(self) -> None:
        async with self._refresh_lock:
            context_outputs: dict[str, str] = {}
            for name, tool in self.config.tools.context.items():
                result = await self.command_runner.run(tool, [])
                context_outputs[name] = result.stdout if result.stdout else result.stderr
            self.debug.log("taxonomy_refresh_start", context_outputs=context_outputs)
            try:
                taxonomy = await self.generator.generate(self.config, context_outputs)
            except Exception as exc:
                self.debug.log("taxonomy_refresh_failed", error=str(exc))
                taxonomy = load_taxonomy(self.paths.taxonomy_json) or self.config.seed_taxonomy()
            taxonomy = taxonomy.ensure_fallback(self.config.fallback_category)
            self.runtime.taxonomy = taxonomy
            self.runtime.taxonomy_hash = taxonomy.fingerprint()
            save_taxonomy(self.paths.taxonomy_json, taxonomy)
            self.debug.log(
                "taxonomy_refresh_complete",
                taxonomy_hash=self.runtime.taxonomy_hash,
                categories=sorted(taxonomy.allowed_paths()),
            )

    async def run(self) -> None:
        await self.dbus_service.start()
        await self.refresh_taxonomy()
        initial = await self.provider.snapshot()
        await self.handle_state(initial)
        await asyncio.gather(self._refresh_loop(), self.provider.monitor(self.handle_state))

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.generator.interval_minutes * 60)
            await self.refresh_taxonomy()

    async def handle_state(self, state: ProviderState) -> None:
        self._log_raw_event(state)
        previous_path = self.runtime.status.current_path if self.runtime.status else None
        cache_key = self._decision_key(state, previous_path)
        selected_path = self.decision_cache.get(cache_key)
        self.debug.log(
            "provider_state",
            previous_path=previous_path,
            cache_key=cache_key,
            state=state.model_dump(mode="json", exclude_none=True),
        )
        if selected_path is None:
            selected_path = await self.classifier.classify(
                self.config,
                state,
                self.runtime.taxonomy,
                previous_path,
            )
            self.decision_cache[cache_key] = selected_path
            self.debug.log("classifier_cache_store", cache_key=cache_key, selected_path=selected_path)
        else:
            self.debug.log("classifier_cache_hit", cache_key=cache_key, selected_path=selected_path)
        if previous_path == selected_path:
            self.debug.log("activity_unchanged", selected_path=selected_path)
            return
        now = utcnow()
        await self._close_previous_span(now)
        await self._run_actions(selected_path)
        top_node, _ = self.runtime.taxonomy.node_for_path(selected_path)
        status = StatusRecord(
            current_path=selected_path,
            top_level=selected_path.split("/", 1)[0],
            icon=top_node.icon,
            updated_at=now,
            taxonomy_hash=self.runtime.taxonomy_hash,
        )
        self.runtime.status = status
        self.runtime.last_changed_at = now
        save_status(self.paths.status_json, status)
        self.dbus_service.update_status(status)
        self.debug.log(
            "activity_changed",
            previous_path=previous_path,
            selected_path=selected_path,
            top_level=status.top_level,
            taxonomy_hash=self.runtime.taxonomy_hash,
        )
        append_jsonl(
            self.paths.activity_log,
            {
                "ts": now.isoformat(),
                "event": "activity_change",
                "path": selected_path,
                "top_level": status.top_level,
                "taxonomy_hash": self.runtime.taxonomy_hash,
                "title": state.focused_window.title if state.focused_window else "",
                "wm_class": state.focused_window.wm_class if state.focused_window else "",
            },
        )

    def _log_raw_event(self, state: ProviderState) -> None:
        window = state.focused_window
        append_jsonl(
            self.paths.raw_events_log,
            {
                "ts": state.timestamp.isoformat(),
                "event": "window_change",
                "screen_locked": state.screen_locked,
                "title": window.title if window else "",
                "wm_class": window.wm_class if window else "",
                "workspace": window.workspace if window else None,
            },
        )

    def _decision_key(self, state: ProviderState, previous_path: str | None) -> str:
        window = state.focused_window
        normalized = {
            "title": window.title if window else "",
            "wm_class": window.wm_class if window else "",
            "workspace": window.workspace if window else None,
            "screen_locked": state.screen_locked,
            "previous_path": previous_path,
            "taxonomy_hash": self.runtime.taxonomy_hash,
        }
        serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

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
        if self.runtime.status is None or self.runtime.last_changed_at is None:
            return
        span = SpanRecord(
            path=self.runtime.status.current_path,
            top_level=self.runtime.status.top_level,
            started_at=self.runtime.last_changed_at,
            ended_at=ended_at,
            duration_seconds=max(0.0, (ended_at - self.runtime.last_changed_at).total_seconds()),
        )
        save_span(self.paths.spans_log, span)

    async def status_payload(self) -> dict[str, Any]:
        status = self.runtime.status
        return {
            "taxonomy_hash": self.runtime.taxonomy_hash,
            "current_path": status.current_path if status else self.config.fallback_category,
            "top_level": status.top_level if status else self.config.fallback_category,
            "icon": status.icon if status else "help-about-symbolic",
            "updated_at": status.updated_at.isoformat() if status else None,
        }
