from __future__ import annotations

from .config import AppConfig
from .constants import UNKNOWN_CHOICE_PATH
from .debug import DebugLogger
from .defaults import CLASSIFIER_BASE_PROMPT
from .llm import LLMError, OpenAICompatibleClient
from .models import ChoiceRegistry, ProviderState, WindowInfo


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
        choices: ChoiceRegistry,
        previous_path: str | None,
    ) -> str:
        if config.classify_idle and state.idle_time_seconds is not None:
            if state.idle_time_seconds >= config.idle_threshold_seconds:
                return "idle"

        allowed_paths = sorted(choices.allowed_paths())
        valid_outputs = allowed_paths + [UNKNOWN_CHOICE_PATH]
        if not allowed_paths:
            return UNKNOWN_CHOICE_PATH

        base_prompt = self._build_prompt(
            config, state, choices, previous_path, valid_outputs
        )
        last_invalid: str | None = None
        for attempt in range(config.classifier.retry_count + 1):
            prompt = base_prompt
            if last_invalid is not None:
                prompt += (
                    "\n\nYour previous answer was invalid.\n"
                    f"Attempt: {attempt}\n"
                    f"Previous answer: {last_invalid}\n"
                    "Valid choices are:\n"
                    + "\n".join(f"- {path}" for path in valid_outputs)
                    + "\nReturn only one valid path exactly."
                )
            try:
                if self.debug is not None:
                    self.debug.log(
                        "classifier_attempt",
                        attempt=attempt,
                        previous_path=previous_path,
                        allowed=valid_outputs,
                        prompt=prompt,
                    )
                result = self.client.chat(
                    config.classifier_model,
                    [{"role": "user", "content": prompt}],
                ).strip()
            except LLMError:
                result = ""
            if self.debug is not None:
                self.debug.log("classifier_result", attempt=attempt, result=result)
            if result in valid_outputs:
                return result
            last_invalid = result or "<empty>"
        if self.debug is not None:
            self.debug.log(
                "classifier_fallback",
                previous_path=previous_path,
                fallback=UNKNOWN_CHOICE_PATH,
                last_invalid=last_invalid,
            )
        return UNKNOWN_CHOICE_PATH

    def _build_prompt(
        self,
        config: AppConfig,
        state: ProviderState,
        choices: ChoiceRegistry,
        previous_path: str | None,
        valid_outputs: list[str],
    ) -> str:
        sections = [
            CLASSIFIER_BASE_PROMPT.strip(),
            "Allowed outputs:\n" + "\n".join(f"- {path}" for path in valid_outputs),
            "Available choices:\n" + choices.describe(),
            f"Previous path: {previous_path or 'none'}",
            "Current event:\n" + self._state_summary(state),
        ]
        supporting_windows = self._supporting_windows_summary(state)
        if supporting_windows:
            sections.append("Supporting open windows:\n" + supporting_windows)
        rendered_instructions = config.render_classifier_instructions().strip()
        if rendered_instructions:
            sections.append("User instructions:\n" + rendered_instructions)
        return "\n\n".join(sections)

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
