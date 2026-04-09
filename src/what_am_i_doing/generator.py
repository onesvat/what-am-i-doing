from __future__ import annotations

from .categories import CATEGORY_CATALOG
from .config import AppConfig
from .debug import DebugLogger
from .defaults import GENERATOR_BASE_PROMPT
from .llm import LLMError, OpenAICompatibleClient
from .models import Taxonomy


class TaxonomyGenerator:
    def __init__(
        self, client: OpenAICompatibleClient, debug: DebugLogger | None = None
    ) -> None:
        self.client = client
        self.debug = debug

    async def generate(
        self, config: AppConfig, context_outputs: dict[str, str]
    ) -> Taxonomy:
        rendered_instructions = config.render_generator_instructions(
            context_outputs
        ).strip()
        prompt = self._build_prompt(config, context_outputs, rendered_instructions)
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
                taxonomy.filter_unknown_action_tools(set(config.tools.actions))
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
    ) -> str:
        category_lines: list[str] = []
        for group in config.configured_category_groups():
            cat_def = next(
                (c for c in CATEGORY_CATALOG if c.name == group.name), None
            )
            if cat_def:
                line = f"- {cat_def.name} (icon: {cat_def.icon}): {cat_def.description}"
                child_names: list[str] = []
                if group.explicit_top and cat_def.subcategories:
                    child_names.extend(cat_def.subcategories)
                child_names.extend(
                    child_name
                    for child_name in group.child_notes
                    if child_name not in child_names
                )
                if child_names:
                    line += f" Subcategories: {', '.join(child_names)}."
                if group.note:
                    line += f" User note: {group.note}"
                category_lines.append(line)
            else:
                note_text = group.note or "no description"
                line = f"- {group.name}: {note_text} (no catalog entry)"
                if group.child_notes:
                    line += (
                        " Subcategories: "
                        + ", ".join(group.child_notes.keys())
                        + "."
                    )
                category_lines.append(line)

        action_tool_lines = [
            f"- {name}: {' '.join(tool.run)}"
            for name, tool in sorted(config.tools.actions.items())
        ]
        context_blocks = [
            f"## {name}\n{output.strip() or '<empty>'}"
            for name, output in sorted(context_outputs.items())
        ]

        learned_lines: list[str] = []
        for rule in config.learned:
            example_text = ""
            if rule.window_example:
                example_parts = []
                if rule.window_example.wm_class:
                    example_parts.append(f"wm_class={rule.window_example.wm_class}")
                if rule.window_example.title:
                    example_parts.append(f"title='{rule.window_example.title[:30]}'")
                if rule.window_example.workspace_name:
                    example_parts.append(
                        f"workspace={rule.window_example.workspace_name}"
                    )
                if example_parts:
                    example_text = f" (example: {', '.join(example_parts)})"
            learned_lines.append(f"- {rule.hint}{example_text}")

        sections = [
            GENERATOR_BASE_PROMPT.strip(),
            "Category definitions:\n"
            + ("\n".join(category_lines) if category_lines else "- none"),
            "Action tool inventory:\n"
            + ("\n".join(action_tool_lines) if action_tool_lines else "- none"),
            "Context outputs:\n"
            + ("\n\n".join(context_blocks) if context_blocks else "None."),
        ]

        if learned_lines:
            sections.append("Learned patterns:\n" + "\n".join(learned_lines))

        if rendered_instructions:
            sections.append("User instructions:\n" + rendered_instructions)
        return "\n\n".join(sections)
