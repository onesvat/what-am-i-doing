from __future__ import annotations

from .config import AppConfig
from .defaults import CLASSIFIER_BASE_PROMPT
from .llm import LLMError, OpenAICompatibleClient
from .models import ProviderState, Taxonomy


class EventClassifier:
    def __init__(self, client: OpenAICompatibleClient) -> None:
        self.client = client

    async def classify(
        self,
        config: AppConfig,
        state: ProviderState,
        taxonomy: Taxonomy,
        previous_path: str | None,
    ) -> str:
        allowed = sorted(taxonomy.allowed_paths())
        base_prompt = self._build_prompt(config, state, taxonomy, previous_path, allowed)
        last_invalid: str | None = None
        for attempt in range(config.classifier.retry_count + 1):
            prompt = base_prompt
            if last_invalid is not None:
                prompt += (
                    "\n\nYour previous answer was invalid.\n"
                    f"Attempt: {attempt}\n"
                    f"Previous answer: {last_invalid}\n"
                    "Valid choices are:\n"
                    + "\n".join(f"- {path}" for path in allowed)
                    + "\nReturn only one valid path exactly."
                )
            try:
                result = self.client.chat(
                    config.model,
                    [{"role": "user", "content": prompt}],
                ).strip()
            except LLMError:
                result = ""
            if result in taxonomy.allowed_paths():
                return result
            last_invalid = result or "<empty>"
        return config.fallback_category

    def _build_prompt(
        self,
        config: AppConfig,
        state: ProviderState,
        taxonomy: Taxonomy,
        previous_path: str | None,
        allowed: list[str],
    ) -> str:
        sections = [
            CLASSIFIER_BASE_PROMPT.strip(),
            "Allowed paths:\n" + "\n".join(f"- {path}" for path in allowed),
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
            f"workspace: {window.workspace}",
            f"workspace_name: {window.workspace_name or ''}",
            f"monitor: {window.monitor or ''}",
            f"fullscreen: {window.fullscreen}",
            f"maximized: {window.maximized}",
        ]
        return "\n".join(parts)
