from __future__ import annotations

from pathlib import Path
import re
from string import Template
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml

from .constants import CONFIG_PATH, FALLBACK_CATEGORY, STATE_DIR
from .models import Taxonomy, TaxonomyNode


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    name: str
    api_key_env: str = "OPENAI_API_KEY"
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
        if not value or "/" in value:
            raise ValueError("category names must be non-empty and cannot contain '/'")
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
    def validate_tool_names(cls, value: dict[str, CommandConfig]) -> dict[str, CommandConfig]:
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


class ClassifierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retry_count: int = 2
    instructions: str = ""
    params: dict[str, str] = Field(default_factory=dict)

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

    @model_validator(mode="after")
    def validate_version_and_categories(self) -> "AppConfig":
        if self.version != 1:
            raise ValueError("only config version 1 is supported")
        names = [category.name for category in self.generator.categories]
        if len(names) != len(set(names)):
            raise ValueError("generator category names must be unique")
        if FALLBACK_CATEGORY not in names:
            self.generator.categories.append(GeneratorCategorySeed(name=FALLBACK_CATEGORY))
        return self

    @property
    def state_dir(self) -> Path:
        return STATE_DIR

    @property
    def fallback_category(self) -> str:
        return FALLBACK_CATEGORY

    def seed_taxonomy(self) -> Taxonomy:
        categories: list[TaxonomyNode] = []
        for category in self.generator.categories:
            categories.append(
                TaxonomyNode(
                    name=category.name,
                    description=category.note or f"Broad {category.name} activity.",
                    icon=_default_icon_for(category.name),
                    tool_calls=[],
                    children=[],
                )
            )
        return Taxonomy(categories=categories).ensure_fallback()

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
    categories = [
        {"name": name, "note": note}
        for name, note in category_notes.items()
        if name != FALLBACK_CATEGORY
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
                    name: tool.model_dump(mode="python") for name, tool in context_tools.items()
                },
                "actions": {
                    name: tool.model_dump(mode="python") for name, tool in action_tools.items()
                },
            },
        }
    )


def _default_icon_for(name: str) -> str:
    icons = {
        "coding": "laptop-symbolic",
        "messaging": "mail-unread-symbolic",
        "planning": "view-calendar-symbolic",
        "surfing": "web-browser-symbolic",
        "adult": "dialog-warning-symbolic",
        FALLBACK_CATEGORY: "help-about-symbolic",
    }
    return icons.get(name, "applications-system-symbolic")
