from __future__ import annotations

from .config import AppConfig
from .debug import DebugLogger
from .defaults import GENERATOR_BASE_PROMPT
from .llm import LLMError, OpenAICompatibleClient
from .models import AppPaths, CorrectionRecord, Taxonomy
from .storage import load_recent_corrections


class TaxonomyGenerator:
    def __init__(self, client: OpenAICompatibleClient, debug: DebugLogger | None = None) -> None:
        self.client = client
        self.debug = debug

    async def generate(self, config: AppConfig, context_outputs: dict[str, str]) -> Taxonomy:
        paths = AppPaths.from_state_dir(config.state_dir)
        corrections = load_recent_corrections(
            paths.corrections_log, config.classifier.correction_retention_days
        )
        rendered_instructions = config.render_generator_instructions(context_outputs).strip()
        prompt = self._build_prompt(config, context_outputs, rendered_instructions, corrections)
        last_error: Exception | None = None
        for attempt in range(config.generator.retry_count + 1):
            try:
                if self.debug is not None:
                    self.debug.log(
                        "generator_attempt",
                        attempt=attempt,
                        context_outputs=context_outputs,
                        prompt=prompt,
                    )
                content = self.client.chat(
                    config.generator_model,
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                )
                taxonomy = Taxonomy.model_validate_json(content)
                taxonomy = config.normalize_generated_taxonomy(taxonomy)
                taxonomy.validate_action_tool_refs(set(config.tools.actions))
                if self.debug is not None:
                    self.debug.log(
                        "generator_result",
                        attempt=attempt,
                        taxonomy=taxonomy.model_dump(mode="json", exclude_none=True),
                    )
                return taxonomy
            except (LLMError, ValueError) as exc:
                last_error = exc
                if self.debug is not None:
                    self.debug.log("generator_error", attempt=attempt, error=str(exc))
        raise RuntimeError(f"generator failed: {last_error}") from last_error

    def _build_prompt(
        self,
        config: AppConfig,
        context_outputs: dict[str, str],
        rendered_instructions: str,
        corrections: list[CorrectionRecord] | None = None,
    ) -> str:
        category_lines = [
            f"- {category.name}: {category.note or 'no extra note'}"
            for category in config.generator.categories
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
            "Broad category hints:\n" + ("\n".join(category_lines) if category_lines else "- none"),
            "Action tool inventory:\n" + ("\n".join(action_tool_lines) if action_tool_lines else "- none"),
            "Context outputs:\n" + ("\n\n".join(context_blocks) if context_blocks else "None."),
        ]

        if corrections:
            correction_lines = []
            for c in corrections[-20:]:  # More for generator
                win = c.state.focused_window
                if win:
                    correction_lines.append(
                        f"- Window Title: \"{win.title}\", Class: \"{win.wm_class}\" -> "
                        f"user corrected to \"{c.manual_path}\""
                    )
            if correction_lines:
                sections.append(
                    "User's manual classification corrections (ensure taxonomy supports these needs):\n"
                    + "\n".join(correction_lines)
                )

        if rendered_instructions:
            sections.append("User instructions:\n" + rendered_instructions)
        return "\n\n".join(sections)
