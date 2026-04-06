from __future__ import annotations

from .config import AppConfig
from .constants import PANEL_KIND_UNCLASSIFIED
from .debug import DebugLogger
from .defaults import CLASSIFIER_BASE_PROMPT
from .llm import LLMError, OpenAICompatibleClient
from .models import ProviderState, Taxonomy


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
        taxonomy: Taxonomy,
        previous_path: str | None,
    ) -> str:
        allowed_paths = sorted(taxonomy.allowed_paths())
        valid_outputs = allowed_paths + [PANEL_KIND_UNCLASSIFIED]
        base_prompt = self._build_prompt(
            config, state, taxonomy, previous_path, valid_outputs
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
                fallback=PANEL_KIND_UNCLASSIFIED,
                last_invalid=last_invalid,
            )
        return PANEL_KIND_UNCLASSIFIED

    def _build_prompt(
        self,
        config: AppConfig,
        state: ProviderState,
        taxonomy: Taxonomy,
        previous_path: str | None,
        valid_outputs: list[str],
    ) -> str:
        sections = [
            CLASSIFIER_BASE_PROMPT.strip(),
            "Allowed outputs:\n" + "\n".join(f"- {path}" for path in valid_outputs),
            "Taxonomy details:\n" + taxonomy.describe(),
            f"Previous path: {previous_path or 'none'}",
            "Current event:\n" + self._state_summary(state),
        ]
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
            f"workspace_name: {window.workspace_name or ''}",
            f"active_workspace_name: {state.active_workspace_name or ''}",
            f"fullscreen: {window.fullscreen}",
            f"maximized: {window.maximized}",
            f"screen_locked: {state.screen_locked}",
            f"idle_time_seconds: {state.idle_time_seconds or 0}",
        ]
        return "\n".join(parts)
