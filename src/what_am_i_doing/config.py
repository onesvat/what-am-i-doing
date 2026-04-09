from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from string import Template
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml

from .constants import CONFIG_PATH, IDLE_ICON, RESERVED_CATEGORY_NAMES, STATE_DIR
from .models import Taxonomy, TaxonomyNode


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(slots=True)
class ConfiguredCategoryGroup:
    name: str
    note: str = ""
    explicit_top: bool = False
    child_notes: dict[str, str] = field(default_factory=dict)


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

    def configured_category_groups(self) -> list[ConfiguredCategoryGroup]:
        groups: dict[str, ConfiguredCategoryGroup] = {}
        for category in self.generator.categories:
            top, _, child = category.name.partition("/")
            group = groups.setdefault(top, ConfiguredCategoryGroup(name=top))
            if child:
                group.child_notes.setdefault(child, category.note)
                continue
            group.explicit_top = True
            if category.note:
                group.note = category.note
        return list(groups.values())

    def seed_taxonomy(self) -> Taxonomy:
        categories = [
            self._seed_node_for_group(group) for group in self.configured_category_groups()
        ]
        return Taxonomy(categories=categories)

    def normalize_generated_taxonomy(self, taxonomy: Taxonomy) -> Taxonomy:
        canonical_taxonomy = self._canonicalize_taxonomy(taxonomy)
        existing = {node.name: node for node in canonical_taxonomy.categories}
        categories: list[TaxonomyNode] = []
        for group in self.configured_category_groups():
            node = existing.get(group.name)
            if node is None:
                categories.append(self._seed_node_for_group(group))
                continue
            normalized_node = self._normalize_node_with_catalog(node, group)
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

    def _canonicalize_taxonomy(self, taxonomy: Taxonomy) -> Taxonomy:
        categories: list[TaxonomyNode] = []
        by_name: dict[str, TaxonomyNode] = {}
        for node in taxonomy.categories:
            top, _, child = node.name.partition("/")
            if child:
                parent = self._ensure_root_node(categories, by_name, top)
                self._merge_child_node(
                    parent,
                    TaxonomyNode(
                        name=child,
                        description=node.description
                        or self._configured_child_description(top, child),
                        icon=node.icon or self._default_icon_for_path(f"{top}/{child}"),
                        tool_calls=list(node.tool_calls or []),
                        children=list(node.children or []),
                    ),
                )
                continue

            parent = self._ensure_root_node(categories, by_name, node.name)
            parent.description = node.description or parent.description
            parent.icon = node.icon or parent.icon
            if node.tool_calls:
                parent.tool_calls = list(node.tool_calls)
            for child_node in node.children or []:
                child_name = self._canonical_child_name(node.name, child_node.name)
                self._merge_child_node(
                    parent,
                    TaxonomyNode(
                        name=child_name,
                        description=child_node.description
                        or self._configured_child_description(node.name, child_name),
                        icon=child_node.icon
                        or self._default_icon_for_path(f"{node.name}/{child_name}"),
                        tool_calls=list(child_node.tool_calls or []),
                        children=list(child_node.children or []),
                    ),
                )
        return Taxonomy(categories=categories)

    def _ensure_root_node(
        self,
        categories: list[TaxonomyNode],
        by_name: dict[str, TaxonomyNode],
        name: str,
    ) -> TaxonomyNode:
        node = by_name.get(name)
        if node is not None:
            return node
        node = TaxonomyNode(
            name=name,
            description=self._configured_top_description(name),
            icon=self._default_icon_for_path(name),
            tool_calls=[],
            children=[],
        )
        by_name[name] = node
        categories.append(node)
        return node

    def _merge_child_node(self, parent: TaxonomyNode, child: TaxonomyNode) -> None:
        for existing in parent.children:
            if existing.name != child.name:
                continue
            existing.description = child.description or existing.description
            existing.icon = child.icon or existing.icon
            if child.tool_calls:
                existing.tool_calls = list(child.tool_calls)
            if child.children:
                existing.children = list(child.children)
            return
        parent.children.append(child)

    def _seed_node_for_group(self, group: ConfiguredCategoryGroup) -> TaxonomyNode:
        from .categories import get_category_definition

        cat_def = get_category_definition(group.name)
        children: list[TaxonomyNode] = []
        if group.explicit_top and cat_def is not None and cat_def.subcategories:
            child_names = list(cat_def.subcategories)
            child_names.extend(
                child_name
                for child_name in group.child_notes
                if child_name not in cat_def.subcategories
            )
        else:
            child_names = list(group.child_notes)

        for child_name in child_names:
            children.append(
                TaxonomyNode(
                    name=child_name,
                    description=self._configured_child_description(
                        group.name, child_name, group.child_notes.get(child_name, "")
                    ),
                    icon=self._default_icon_for_path(f"{group.name}/{child_name}"),
                    tool_calls=[],
                    children=[],
                )
            )

        if group.explicit_top and children:
            children.append(self._other_child_for(group.name))

        return TaxonomyNode(
            name=group.name,
            description=self._configured_top_description(group.name, group.note),
            icon=self._default_icon_for_path(group.name),
            tool_calls=[],
            children=children,
        )

    def _normalize_node_with_catalog(
        self, node: TaxonomyNode, group: ConfiguredCategoryGroup
    ) -> TaxonomyNode:
        from .categories import (
            get_category_definition,
        )

        children = list(node.children or [])
        parent_tool_calls = list(node.tool_calls or [])

        cat_def = get_category_definition(node.name)
        if not group.explicit_top and group.child_notes:
            allowed = set(group.child_notes)
            children = [
                child
                for child in children
                if self._canonical_child_name(node.name, child.name) in allowed
            ]

        known_child_names = {
            self._canonical_child_name(node.name, child.name) for child in children
        }
        for child_name, note in group.child_notes.items():
            if child_name in known_child_names:
                continue
            children.append(
                TaxonomyNode(
                    name=child_name,
                    description=self._configured_child_description(
                        node.name, child_name, note
                    ),
                    icon=self._default_icon_for_path(f"{node.name}/{child_name}"),
                    tool_calls=[],
                    children=[],
                )
            )

        children = [
            child
            for child in children
            if self._canonical_child_name(node.name, child.name) != "other"
        ]
        should_have_other = False
        if group.explicit_top:
            has_predefined_subs = (
                cat_def is not None and cat_def.subcategories is not None
            )
            should_have_other = has_predefined_subs or len(children) > 0

        if should_have_other:
            other_child = next(
                (
                    child
                    for child in node.children or []
                    if self._canonical_child_name(node.name, child.name) == "other"
                ),
                None,
            )
            if other_child is None:
                children.append(self._other_child_for(node.name, parent_tool_calls))
            else:
                children.append(
                    TaxonomyNode(
                        name="other",
                        description=other_child.description
                        or self._other_child_for(node.name).description,
                        icon=other_child.icon
                        or self._default_icon_for_path(node.name),
                        tool_calls=list(other_child.tool_calls or parent_tool_calls),
                        children=list(other_child.children or []),
                    )
                )

        has_children = len(children) > 0
        tool_calls = [] if has_children else parent_tool_calls

        normalized_children = [
            self._normalize_child_node(child, node.name) for child in children
        ]

        return TaxonomyNode(
            name=node.name,
            description=node.description
            or self._configured_top_description(node.name, group.note),
            icon=self._default_icon_for_path(node.name),
            tool_calls=tool_calls,
            children=normalized_children,
        )

    def _normalize_child_node(
        self, child: TaxonomyNode, parent_name: str
    ) -> TaxonomyNode:
        child_name = self._canonical_child_name(parent_name, child.name)
        child_path = f"{parent_name}/{child_name}"
        return TaxonomyNode(
            name=child_name,
            description=child.description
            or self._configured_child_description(parent_name, child_name),
            icon=child.icon or self._default_icon_for_path(child_path),
            tool_calls=child.tool_calls or [],
            children=child.children or [],
        )

    def _configured_top_description(self, name: str, note: str = "") -> str:
        from .categories import get_description_for_path

        description = get_description_for_path(name)
        if note:
            if description.startswith("Broad "):
                return note
            if note not in description:
                return f"{description} {note}".strip()
        return description

    def _configured_child_description(
        self, parent_name: str, child_name: str, note: str = ""
    ) -> str:
        from .categories import get_description_for_path

        if note:
            return note
        path = f"{parent_name}/{child_name}"
        description = get_description_for_path(path)
        if description == get_description_for_path(parent_name):
            return f"Specific {parent_name} activity: {child_name.replace('_', ' ')}."
        if description.startswith("Broad "):
            return f"Specific {parent_name} activity: {child_name.replace('_', ' ')}."
        return description

    def _other_child_for(
        self, parent_name: str, tool_calls: list[Any] | None = None
    ) -> TaxonomyNode:
        return TaxonomyNode(
            name="other",
            description=f"General {parent_name} activities not matching specific subcategories.",
            icon=self._default_icon_for_path(parent_name),
            tool_calls=list(tool_calls or []),
            children=[],
        )

    def _canonical_child_name(self, parent_name: str, child_name: str) -> str:
        if child_name.startswith(f"{parent_name}/"):
            return child_name[len(parent_name) + 1 :]
        return child_name

    def _default_icon_for_path(self, path: str) -> str:
        from .categories import get_icon_for_path

        return get_icon_for_path(path)

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
