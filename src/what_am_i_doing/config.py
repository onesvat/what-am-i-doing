from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from .constants import CONFIG_PATH, STATE_DIR
from .models import ChoiceDefinition, ChoiceRegistry, ToolCall


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    name: str
    api_key_env: str = ""
    api_key: str = ""
    timeout_seconds: int = 30
    temperature: float = 0.0


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

    actions: dict[str, CommandConfig] = Field(default_factory=dict)


class ClassifierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retry_count: int = 2
    instructions: str = ""
    model: ModelConfig | None = None


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 2
    model: ModelConfig
    classifier: ClassifierConfig
    choices: list[ChoiceDefinition] = Field(default_factory=list)
    tools: ToolRegistry = Field(default_factory=ToolRegistry)
    idle_threshold_seconds: int = 60
    classify_idle: bool = True

    @model_validator(mode="after")
    def validate_config(self) -> "AppConfig":
        if self.version != 2:
            raise ValueError("only config version 2 is supported")
        paths = [choice.path for choice in self.choices]
        if len(paths) != len(set(paths)):
            raise ValueError("choice paths must be unique")
        known_tools = set(self.tools.actions)
        for choice in self.choices:
            for action in choice.actions:
                if action.tool not in known_tools:
                    raise ValueError(
                        f"choice action references unknown tool: {action.tool}"
                    )
        return self

    @property
    def classifier_model(self) -> ModelConfig:
        return self.classifier.model or self.model

    @property
    def state_dir(self) -> Path:
        return STATE_DIR

    def choice_registry(self) -> ChoiceRegistry:
        return ChoiceRegistry(
            choices=[
                ChoiceDefinition.model_validate(
                    choice.model_dump(mode="python", exclude_none=True)
                )
                for choice in self.choices
            ]
        )

    def render_classifier_instructions(self) -> str:
        return self.classifier.instructions


def default_config_path() -> Path:
    return CONFIG_PATH


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path).expanduser() if path else default_config_path()
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("config root must be a mapping")
    raw = resolve_choice_imports(raw, config_path.parent)
    return AppConfig.model_validate(raw)


def resolve_choice_imports(raw: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    raw = dict(raw)
    choices = raw.get("choices")
    if choices is None:
        raw["choices"] = []
        return raw
    if not isinstance(choices, list):
        raise ValueError("choices must be a list")
    raw["choices"] = _resolve_choice_items(choices, config_dir, seen_files=())
    return raw


def _resolve_choice_items(
    items: list[Any], config_dir: Path, *, seen_files: tuple[Path, ...]
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("choices entries must be mappings")
        if "import" in item:
            import_path = _resolve_import_path(str(item["import"]), config_dir)
            if import_path in seen_files:
                raise ValueError(f"choice import loop detected: {import_path}")
            resolved.extend(
                _load_imported_choices(import_path, seen_files=seen_files + (import_path,))
            )
            continue
        resolved.append(item)
    return resolved


def _load_imported_choices(
    path: Path, *, seen_files: tuple[Path, ...]
) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"choice import not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        imported = yaml.safe_load(handle) or []
    if not isinstance(imported, list):
        raise ValueError(f"choice import must contain a list: {path}")
    return _resolve_choice_items(imported, path.parent, seen_files=seen_files)


def _resolve_import_path(import_path: str, config_dir: Path) -> Path:
    path = Path(import_path).expanduser()
    if not path.is_absolute():
        path = config_dir / path
    return path.resolve()


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False)


def save_config(path: str | Path, config: AppConfig) -> None:
    config_path = Path(path).expanduser()
    config_path.write_text(render_config(config), encoding="utf-8")


def render_config(config: AppConfig) -> str:
    payload = config.model_dump(mode="python", exclude_none=True)
    header = (
        "# waid config\n"
        "# Add direct choices under `choices`, or use `- import: path/to/choices.yaml`.\n"
        "# Imported files must return the same flat choice shape.\n"
        "# The classifier must return one configured path or `unknown`.\n\n"
    )
    return header + dump_yaml(payload)


def build_minimal_config(
    *,
    base_url: str,
    model_name: str,
    api_key_env: str,
) -> AppConfig:
    return AppConfig.model_validate(
        {
            "version": 2,
            "model": {
                "base_url": base_url,
                "name": model_name,
                "api_key_env": api_key_env,
            },
            "classifier": {
                "instructions": "",
            },
            "choices": [],
            "tools": {"actions": {}},
            "idle_threshold_seconds": 60,
            "classify_idle": True,
        }
    )
