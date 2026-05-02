from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from .activity_catalog import builtin_activity_entries
from .constants import CONFIG_PATH, STATE_DIR, TASKS_PATH
from .models import CatalogEntry, SelectionCatalog


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


class SyncConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: list[str] = Field(default_factory=list)
    interval_minutes: int = 5


class ScreenshotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_retention: int = 50


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 2
    model: ModelConfig
    classifier: ClassifierConfig
    activities: list[CatalogEntry] = Field(default_factory=list)
    allow_activities: list[str] = Field(default_factory=list)
    block_activities: list[str] = Field(default_factory=list)
    tools: ToolRegistry = Field(default_factory=ToolRegistry)
    idle_threshold_seconds: int = 60
    classify_idle: bool = True
    screenshot: ScreenshotConfig = Field(default_factory=ScreenshotConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)

    @model_validator(mode="after")
    def validate_config(self) -> "AppConfig":
        if self.version != 2:
            raise ValueError("only config version 2 is supported")

        builtin_paths = {entry.path for entry in builtin_activity_entries()}
        allow = set(self.allow_activities)
        block = set(self.block_activities)
        overlap = sorted(allow & block)
        if overlap:
            raise ValueError(
                "activity allow/block overlap is invalid: " + ", ".join(overlap)
            )
        unknown_filters = sorted((allow | block) - builtin_paths)
        if unknown_filters:
            raise ValueError(
                "unknown built-in activity ids: " + ", ".join(unknown_filters)
            )

        custom_paths = [entry.path for entry in self.activities]
        colliding = sorted(set(custom_paths) & builtin_paths)
        if colliding:
            raise ValueError(
                "custom activities cannot override built-ins: " + ", ".join(colliding)
            )

        known_tools = set(self.tools.actions)
        for entry in self.activities:
            for action in entry.actions:
                if action.tool not in known_tools:
                    raise ValueError(
                        f"entry action references unknown tool: {action.tool}"
                    )
        return self

    @property
    def classifier_model(self) -> ModelConfig:
        return self.classifier.model or self.model

    @property
    def state_dir(self) -> Path:
        return STATE_DIR

    def activity_catalog(self) -> SelectionCatalog:
        builtin = builtin_activity_entries()
        allow = set(self.allow_activities)
        block = set(self.block_activities)
        enabled_builtin = [
            entry
            for entry in builtin
            if (not allow or entry.path in allow) and entry.path not in block
        ]
        return SelectionCatalog(
            activity_entries=enabled_builtin
            + [
                CatalogEntry.model_validate(
                    entry.model_dump(mode="python", exclude_none=True)
                )
                for entry in self.activities
            ],
        )

    def render_classifier_instructions(self) -> str:
        return self.classifier.instructions


def default_config_path() -> Path:
    return CONFIG_PATH


def default_tasks_path() -> Path:
    return TASKS_PATH


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path).expanduser() if path else default_config_path()
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("config root must be a mapping")
    return AppConfig.model_validate(raw)


def load_tasks(path: str | Path | None = None) -> list[CatalogEntry]:
    tasks_path = Path(path).expanduser() if path else default_tasks_path()
    if not tasks_path.exists():
        return []
    with tasks_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or []
    if not isinstance(raw, list):
        raise ValueError("tasks root must be a list")
    entries = [CatalogEntry.model_validate(item) for item in raw]
    paths = [entry.path for entry in entries]
    if len(paths) != len(set(paths)):
        raise ValueError("task paths must be unique")
    return entries


def build_selection_catalog(
    config: AppConfig,
    tasks: list[CatalogEntry] | None = None,
) -> SelectionCatalog:
    task_entries = tasks or []
    catalog = config.activity_catalog()
    combined_paths = catalog.activity_paths() | {entry.path for entry in task_entries}
    if len(combined_paths) != len(catalog.activity_paths()) + len(task_entries):
        raise ValueError("activity and task paths must be unique")
    known_tools = set(config.tools.actions)
    for entry in task_entries:
        for action in entry.actions:
            if action.tool not in known_tools:
                raise ValueError(f"entry action references unknown tool: {action.tool}")
    return SelectionCatalog(
        activity_entries=catalog.activity_entries,
        task_entries=[
            CatalogEntry.model_validate(entry.model_dump(mode="python", exclude_none=True))
            for entry in task_entries
        ],
    )


def dump_yaml(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False)


def save_config(path: str | Path, config: AppConfig) -> None:
    config_path = Path(path).expanduser()
    config_path.write_text(render_config(config), encoding="utf-8")


def render_config(config: AppConfig) -> str:
    payload = config.model_dump(mode="python", exclude_none=True)
    header = (
        "# waid config\n"
        "# Built-in activities live in the app.\n"
        "# Use allow_activities/block_activities to filter built-ins.\n"
        "# Use activities for custom activity definitions.\n"
        "# Tasks live in ~/.waid/tasks.yaml.\n\n"
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
            "activities": [],
            "allow_activities": [],
            "block_activities": [],
            "tools": {"actions": {}},
            "idle_threshold_seconds": 60,
            "classify_idle": True,
        }
    )
