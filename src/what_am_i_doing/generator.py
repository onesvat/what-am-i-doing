from __future__ import annotations

from .config import AppConfig
from .defaults import GENERATOR_BASE_PROMPT
from .llm import LLMError, OpenAICompatibleClient
from .models import Taxonomy


class TaxonomyGenerator:
    def __init__(self, client: OpenAICompatibleClient) -> None:
        self.client = client

    async def generate(self, config: AppConfig, context_outputs: dict[str, str]) -> Taxonomy:
        rendered_instructions = config.render_generator_instructions(
            {
                **context_outputs,
                "fallback_category": config.fallback_category,
            }
        ).strip()
        prompt = self._build_prompt(config, context_outputs, rendered_instructions)
        last_error: Exception | None = None
        for _ in range(config.generator.retry_count + 1):
            try:
                content = self.client.chat(
                    config.model,
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                taxonomy = Taxonomy.model_validate_json(content).ensure_fallback(config.fallback_category)
                taxonomy.validate_action_tool_refs(set(config.tools.actions))
                return taxonomy
            except (LLMError, ValueError) as exc:
                last_error = exc
        raise RuntimeError(f"generator failed: {last_error}") from last_error

    def _build_prompt(
        self,
        config: AppConfig,
        context_outputs: dict[str, str],
        rendered_instructions: str,
    ) -> str:
        category_lines = [
            f"- {category.name}: {category.note or 'no extra note'}"
            for category in config.generator.categories
            if category.name != config.fallback_category
        ]
        action_tool_lines = [
            f"- {name}: {' '.join(tool.run)}"
            for name, tool in sorted(config.tools.actions.items())
        ]
        context_blocks = [
            f"## {name}\n{output.strip() or '<empty>'}"
            for name, output in sorted(context_outputs.items())
        ]
        sections = [
            GENERATOR_BASE_PROMPT.strip(),
            f"Fallback category: {config.fallback_category}",
            "Broad category hints:\n" + ("\n".join(category_lines) if category_lines else "- none"),
            "Action tool inventory:\n" + ("\n".join(action_tool_lines) if action_tool_lines else "- none"),
            "Context outputs:\n" + ("\n\n".join(context_blocks) if context_blocks else "None."),
        ]
        if rendered_instructions:
            sections.append("User instructions:\n" + rendered_instructions)
        return "\n\n".join(sections)
