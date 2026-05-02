from __future__ import annotations

import base64
import json

from pathlib import Path

from .config import AppConfig
from .constants import UNKNOWN_PATH
from .debug import DebugLogger
from .defaults import CLASSIFIER_BASE_PROMPT
from .llm import LLMError, OpenAICompatibleClient, build_vision_message
from .models import (
    ClassificationResult,
    ProviderState,
    SelectionCatalog,
    WindowInfo,
)


class EventClassifier:
    def __init__(
        self, client: OpenAICompatibleClient, debug: DebugLogger | None = None
    ) -> None:
        self.client = client
        self.debug = debug

    async def classify(
        self,
        config: AppConfig,
        state: ProviderState,
        catalog: SelectionCatalog,
        previous_result: ClassificationResult | None,
        screenshot_path: str | None = None,
    ) -> ClassificationResult:
        if config.classify_idle and state.idle_time_seconds is not None:
            if state.idle_time_seconds >= config.idle_threshold_seconds:
                return ClassificationResult(activity_path="idle", task_path=None)

        activity_outputs = sorted(catalog.activity_paths())
        task_outputs = sorted(catalog.task_paths())
        if not activity_outputs:
            return ClassificationResult(activity_path=UNKNOWN_PATH, task_path=None)

        base_prompt = self._build_prompt(
            config,
            state,
            catalog,
            previous_result,
            activity_outputs,
            task_outputs,
        )
        last_invalid = "<empty>"
        for attempt in range(config.classifier.retry_count + 1):
            prompt = base_prompt
            if attempt > 0:
                prompt += (
                    "\n\nPrevious answer invalid.\n"
                    f"Attempt: {attempt}\n"
                    f"Previous answer: {last_invalid}\n"
                    "Return valid JSON with an allowed `activity_path` and optional `task_path`."
                )
            try:
                if self.debug is not None:
                    self.debug.log(
                        "classifier_attempt",
                        attempt=attempt,
                        previous_result=previous_result.model_dump(mode="json")
                        if previous_result is not None
                        else None,
                        activity_outputs=activity_outputs,
                        task_outputs=task_outputs,
                        prompt=prompt,
                    )
                messages = self._build_messages(config, prompt, screenshot_path)
                raw_result = self.client.chat(
                    config.classifier_model,
                    messages,
                    json_mode=True,
                ).strip()
            except LLMError:
                raw_result = ""
            if self.debug is not None:
                self.debug.log("classifier_result", attempt=attempt, result=raw_result)
            parsed = self._parse_result(raw_result, activity_outputs, task_outputs)
            if parsed is not None:
                return parsed
            last_invalid = raw_result or "<empty>"
        if self.debug is not None:
            self.debug.log(
                "classifier_fallback",
                previous_result=previous_result.model_dump(mode="json")
                if previous_result is not None
                else None,
                fallback=UNKNOWN_PATH,
                last_invalid=last_invalid,
            )
        return ClassificationResult(activity_path=UNKNOWN_PATH, task_path=None)

    def _parse_result(
        self,
        raw_result: str,
        activity_outputs: list[str],
        task_outputs: list[str],
    ) -> ClassificationResult | None:
        try:
            payload = json.loads(_strip_fences(raw_result))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        activity_path = payload.get("activity_path")
        task_path = payload.get("task_path")
        if not isinstance(activity_path, str):
            return None
        if activity_path not in set(activity_outputs) | {"idle", UNKNOWN_PATH}:
            return None
        if task_path is not None and not isinstance(task_path, str):
            return None
        if task_path is not None and task_path not in task_outputs:
            return None
        if activity_path in {"idle", UNKNOWN_PATH}:
            task_path = None
        return ClassificationResult(activity_path=activity_path, task_path=task_path)

    def _build_prompt(
        self,
        config: AppConfig,
        state: ProviderState,
        catalog: SelectionCatalog,
        previous_result: ClassificationResult | None,
        activity_outputs: list[str],
        task_outputs: list[str],
    ) -> str:
        sections = [
            CLASSIFIER_BASE_PROMPT.strip(),
            "Allowed activity_path values:\n"
            + "\n".join(f"- {path}" for path in activity_outputs + ["idle", UNKNOWN_PATH]),
            "Allowed task_path values:\n"
            + ("\n".join(f"- {path}" for path in task_outputs) if task_outputs else "- null")
            + "\n- null",
            "Activities:\n" + catalog.describe_activities(),
            "Tasks:\n" + (catalog.describe_tasks() if task_outputs else "- No tasks available."),
            "Current event:\n" + self._state_summary(state),
        ]
        rendered_instructions = config.render_classifier_instructions().strip()
        if rendered_instructions:
            sections.append("User instructions:\n" + rendered_instructions)
        sections.append(
            'Example JSON: {"activity_path":"coding/terminal","task_path":"example-task"}'
        )
        return "\n\n".join(sections)

    def _build_messages(
        self, config: AppConfig, prompt: str, screenshot_path: str | None
    ) -> list[dict]:
        if screenshot_path and config.screenshot.enabled:
            path = Path(screenshot_path)
            if path.exists():
                try:
                    image_data = base64.b64encode(path.read_bytes()).decode("utf-8")
                    return [build_vision_message(prompt, image_data)]
                except Exception:
                    pass
        return [{"role": "user", "content": prompt}]

    def _state_summary(self, state: ProviderState) -> str:
        if state.screen_locked:
            return "screen_locked: true"
        window = state.focused_window
        if window is None:
            return "focused_window: none"
        parts = [
            f"title: {window.title}",
            f"wm_class: {window.wm_class}",
            f"wm_class_instance: {window.wm_class_instance or ''}",
            f"app_id: {window.app_id or ''}",
            f"workspace: {window.workspace if window.workspace is not None else ''}",
            f"workspace_name: {window.workspace_name or ''}",
            f"active_workspace_name: {state.active_workspace_name or ''}",
            f"fullscreen: {window.fullscreen}",
            f"maximized: {window.maximized}",
            f"screen_locked: {state.screen_locked}",
            f"idle_time_seconds: {state.idle_time_seconds or 0}",
        ]
        return "\n".join(parts)

    def _supporting_windows_summary(self, state: ProviderState) -> str:
        focused = state.focused_window
        if focused is None or not state.open_windows:
            return ""

        focus_workspace = (
            focused.workspace
            if focused.workspace is not None
            else state.active_workspace
        )
        seen: set[tuple[int | None, str, str]] = set()
        lines: list[str] = []
        candidates = sorted(
            state.open_windows,
            key=lambda window: (
                window.z_order is None,
                window.z_order if window.z_order is not None else 9999,
            ),
        )
        for window in candidates:
            if self._same_window(window, focused):
                continue
            if not window.title and not window.wm_class:
                continue
            if (
                focus_workspace is not None
                and window.workspace is not None
                and window.workspace != focus_workspace
            ):
                continue
            dedupe_key = (window.pid, window.wm_class, window.title)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            label = window.wm_class or "unknown"
            title = window.title or "<untitled>"
            suffix = []
            if window.workspace_name:
                suffix.append(f"workspace={window.workspace_name}")
            if window.app_id:
                suffix.append(f"app_id={window.app_id}")
            extra = f" ({', '.join(suffix)})" if suffix else ""
            lines.append(f"- {label}: {title}{extra}")
            if len(lines) == 3:
                break
        return "\n".join(lines)

    def _same_window(self, left: WindowInfo, right: WindowInfo) -> bool:
        return (
            left.pid == right.pid
            and left.wm_class == right.wm_class
            and left.title == right.title
        )


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text
