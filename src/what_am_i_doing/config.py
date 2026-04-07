from __future__ import annotations

from pathlib import Path
import re
from string import Template
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml

from .constants import CONFIG_PATH, IDLE_ICON, RESERVED_CATEGORY_NAMES, STATE_DIR
from .models import Taxonomy, TaxonomyNode


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class WindowExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wm_class: str = ""
    title: str = ""
    app_id: str | None = None
    workspace_name: str | None = None


class LearnedRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hint: str
    target: str
    window_example: WindowExample | None = None

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("target cannot be empty")
        if value.startswith("/") or value.endswith("/"):
            raise ValueError("target cannot start or end with '/'")
        parts = value.split("/")
        for part in parts:
            if not part:
                raise ValueError("target path parts cannot be empty")
        return value


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    name: str
    api_key_env: str = ""
    api_key: str = ""
    timeout_seconds: int = 30
    temperature: float = 0.0


class GeneratorCategorySeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    note: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("category names must be non-empty")
        if value.startswith("/") or value.endswith("/"):
            raise ValueError("category names cannot start or end with '/'")
        parts = value.split("/")
        for part in parts:
            if not part:
                raise ValueError("category path parts cannot be empty")
            if part in RESERVED_CATEGORY_NAMES:
                raise ValueError(f"category name is reserved: {part}")
        return value


class CommandConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: list[str]
    timeout_seconds: int = 10

    @model_validator(mode="after")
    def validate_command(self) -> "CommandConfig":
        if not self.run:
            raise ValueError("command cannot be empty")
        return self


class ToolRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: dict[str, CommandConfig] = Field(default_factory=dict)
    actions: dict[str, CommandConfig] = Field(default_factory=dict)

    @field_validator("context", "actions")
    @classmethod
    def validate_tool_names(
        cls, value: dict[str, CommandConfig]
    ) -> dict[str, CommandConfig]:
        for name in value:
            if not IDENTIFIER_RE.match(name):
                raise ValueError(
                    f"tool names must be identifiers like my_tool; invalid name: {name}"
                )
        return value


class GeneratorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_minutes: int = 5
    retry_count: int = 1
    categories: list[GeneratorCategorySeed] = Field(default_factory=list)
    instructions: str = ""
    model: ModelConfig | None = None


class ClassifierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retry_count: int = 2
    instructions: str = ""
    params: dict[str, str] = Field(default_factory=dict)
    model: ModelConfig | None = None

    @field_validator("params")
    @classmethod
    def validate_param_names(cls, value: dict[str, str]) -> dict[str, str]:
        for name in value:
            if not IDENTIFIER_RE.match(name):
                raise ValueError(
                    f"classifier params must use identifier names like work_mode; invalid name: {name}"
                )
        return value


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    model: ModelConfig
    generator: GeneratorConfig
    classifier: ClassifierConfig
    tools: ToolRegistry = Field(default_factory=ToolRegistry)
    learned: list[LearnedRule] = Field(default_factory=list)
    idle_threshold_seconds: int = 60
    classify_idle: bool = True

    @model_validator(mode="after")
    def validate_version_and_categories(self) -> "AppConfig":
        if self.version != 1:
            raise ValueError("only config version 1 is supported")
        names = [category.name for category in self.generator.categories]
        if len(names) != len(set(names)):
            raise ValueError("generator category names must be unique")
        return self

    @property
    def generator_model(self) -> "ModelConfig":
        return self.generator.model or self.model

    @property
    def classifier_model(self) -> "ModelConfig":
        return self.classifier.model or self.model

    @property
    def state_dir(self) -> Path:
        return STATE_DIR

    def seed_taxonomy(self) -> Taxonomy:
        from .categories import (
            get_description_for_path,
            get_icon_for_path,
            resolve_category_paths,
        )

        paths = [cat.name for cat in self.generator.categories]
        resolved = resolve_category_paths(paths)
        categories: list[TaxonomyNode] = []
        for path in resolved:
            categories.append(
                TaxonomyNode(
                    name=path,
                    description=get_description_for_path(path),
                    icon=get_icon_for_path(path),
                    tool_calls=[],
                    children=[],
                )
            )
        return Taxonomy(categories=categories)

    def normalize_generated_taxonomy(self, taxonomy: Taxonomy) -> Taxonomy:
        from .categories import (
            get_description_for_path,
            get_icon_for_path,
            resolve_category_paths,
        )

        existing = {node.name: node for node in taxonomy.categories}
        paths = [cat.name for cat in self.generator.categories]
        resolved = resolve_category_paths(paths)
        categories: list[TaxonomyNode] = []
        for path in resolved:
            node = existing.get(path)
            if node is None:
                categories.append(
                    TaxonomyNode(
                        name=path,
                        description=get_description_for_path(path),
                        icon=get_icon_for_path(path),
                        tool_calls=[],
                        children=[],
                    )
                )
                continue
            normalized_node = self._normalize_node_with_catalog(node)
            categories.append(normalized_node)
        idle_node = existing.get("idle")
        if idle_node is None:
            categories.append(
                TaxonomyNode(
                    name="idle",
                    description="User is idle (no keyboard/mouse activity)",
                    icon=IDLE_ICON,
                    tool_calls=[],
                    children=[],
                )
            )
        else:
            categories.append(idle_node)
        return Taxonomy(categories=categories)

    def _normalize_node_with_catalog(self, node: TaxonomyNode) -> TaxonomyNode:
        from .categories import get_description_for_path, get_icon_for_path

        children = list(node.children or [])
        has_children = len(children) > 0

        if has_children:
            tool_calls = []
            has_other = any(child.name == "other" for child in children)
            if not has_other:
                children.append(
                    TaxonomyNode(
                        name="other",
                        description=f"General {node.name} activities not matching specific subcategories.",
                        icon=get_icon_for_path(node.name),
                        tool_calls=list(node.tool_calls),
                        children=[],
                    )
                )
            else:
                for i, child in enumerate(children):
                    if child.name == "other" and not child.tool_calls:
                        children[i] = TaxonomyNode(
                            name="other",
                            description=child.description
                            or f"General {node.name} activities not matching specific subcategories.",
                            icon=child.icon or get_icon_for_path(node.name),
                            tool_calls=list(node.tool_calls),
                            children=child.children or [],
                        )
                        break
            normalized_children = [
                self._normalize_child_node(child, node.name) for child in children
            ]
        else:
            tool_calls = node.tool_calls or []
            normalized_children = []

        return TaxonomyNode(
            name=node.name,
            description=node.description or get_description_for_path(node.name),
            icon=get_icon_for_path(node.name),
            tool_calls=tool_calls,
            children=normalized_children,
        )

    def _normalize_child_node(
        self, child: TaxonomyNode, parent_name: str
    ) -> TaxonomyNode:
        from .categories import get_description_for_path, get_icon_for_path

        child_path = f"{parent_name}/{child.name}"
        return TaxonomyNode(
            name=child.name,
            description=child.description or get_description_for_path(child_path),
            icon=child.icon or get_icon_for_path(child_path),
            tool_calls=child.tool_calls or [],
            children=child.children or [],
        )

    def render_generator_instructions(self, variables: dict[str, str]) -> str:
        return interpolate_text(self.generator.instructions, variables)

    def render_classifier_instructions(self) -> str:
        return interpolate_text(self.classifier.instructions, self.classifier.params)


def default_config_path() -> Path:
    return CONFIG_PATH


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path).expanduser() if path else default_config_path()
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(raw)


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False)


def interpolate_text(text: str, variables: dict[str, str]) -> str:
    template = Template(text)
    safe_mapping = {key: value for key, value in variables.items()}
    return template.safe_substitute(safe_mapping)


def parse_target_from_hint(hint: str) -> str:
    hint = hint.strip()
    match = re.search(
        r"should be\s+([A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*)", hint, re.IGNORECASE
    )
    if not match:
        raise ValueError("hint must contain 'should be <path>' pattern")
    return match.group(1)


def save_config(path: str | Path, config: AppConfig) -> None:
    config_path = Path(path).expanduser()
    yaml_content = render_config(config)
    config_path.write_text(yaml_content, encoding="utf-8")


def render_config(config: AppConfig) -> str:
    payload = config.model_dump(mode="python", exclude_none=True)
    header = (
        "# waid config\n"
        "# Context tools are available as ${tool_name} in generator.instructions.\n"
        "# Classifier params are available as ${param_name} in classifier.instructions.\n\n"
    )
    return header + dump_yaml(payload)


def build_minimal_config(
    *,
    base_url: str,
    model_name: str,
    api_key_env: str,
    category_notes: dict[str, str],
    context_tools: dict[str, CommandConfig],
    action_tools: dict[str, CommandConfig],
    generator_instructions: str,
    classifier_instructions: str,
    classifier_params: dict[str, str] | None = None,
) -> AppConfig:
    from .categories import resolve_category_paths, validate_category_path

    paths = [
        name for name in category_notes.keys() if name not in RESERVED_CATEGORY_NAMES
    ]
    valid_paths = [path for path in paths if validate_category_path(path)]
    resolved = resolve_category_paths(valid_paths)
    categories = [
        {"name": path, "note": category_notes.get(path, "")} for path in resolved
    ]

    return AppConfig.model_validate(
        {
            "version": 1,
            "model": {
                "base_url": base_url,
                "name": model_name,
                "api_key_env": api_key_env,
            },
            "generator": {
                "categories": categories,
                "instructions": generator_instructions,
            },
            "classifier": {
                "instructions": classifier_instructions,
                "params": classifier_params or {},
            },
            "tools": {
                "context": {
                    name: tool.model_dump(mode="python")
                    for name, tool in context_tools.items()
                },
                "actions": {
                    name: tool.model_dump(mode="python")
                    for name, tool in action_tools.items()
                },
            },
        }
    )


def _default_icon_for(name: str) -> str:
    from .categories import get_icon_for_path

    return get_icon_for_path(name)
