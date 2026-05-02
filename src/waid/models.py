from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .constants import (
    DISCONNECTED_ICON,
    PANEL_KIND_CLASSIFIED,
    PANEL_KIND_DISCONNECTED,
    PANEL_KIND_PAUSED,
    PANEL_KIND_UNCLASSIFIED,
    PANEL_SCHEMA_VERSION,
    PAUSED_ICON,
    RESERVED_PATHS,
    STATE_DIR,
    UNCLASSIFIED_ICON,
)


@dataclass(slots=True)
class RefreshResult:
    success: bool
    message: str
    used_cached: bool = False


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    args: list[str] = Field(default_factory=list)


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    description: str = ""
    icon: str | None = None
    id: str | None = None
    actions: list[ToolCall] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("entry paths must be non-empty")
        if value.startswith("/") or value.endswith("/"):
            raise ValueError("entry paths cannot start or end with '/'")
        parts = value.split("/")
        for part in parts:
            if not part:
                raise ValueError("entry path parts cannot be empty")
            if part in RESERVED_PATHS:
                raise ValueError(f"entry path is reserved: {part}")
        return value


class SelectionCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_entries: list[CatalogEntry] = Field(default_factory=list)
    task_entries: list[CatalogEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_paths(self) -> "SelectionCatalog":
        paths = [entry.path for entry in self.activity_entries + self.task_entries]
        if len(paths) != len(set(paths)):
            raise ValueError("entry paths must be unique")
        return self

    def allowed_paths(self) -> set[str]:
        return self.activity_paths() | self.task_paths()

    def activity_paths(self) -> set[str]:
        return {entry.path for entry in self.activity_entries}

    def task_paths(self) -> set[str]:
        return {entry.path for entry in self.task_entries}

    def task_path_to_id(self, path: str) -> str | None:
        for entry in self.task_entries:
            if entry.path == path and entry.id:
                return entry.id
        return None

    def entry_for_path(self, path: str) -> CatalogEntry:
        for entry in self.activity_entries + self.task_entries:
            if entry.path == path:
                return entry
        raise KeyError(path)

    def actions_for_path(self, path: str) -> list[ToolCall]:
        return list(self.entry_for_path(path).actions)

    def describe_activities(self) -> str:
        return "\n".join(
            f"- {entry.path}: {entry.description or 'No description.'}"
            for entry in self.activity_entries
        )

    def describe_tasks(self) -> str:
        lines = []
        for entry in self.task_entries:
            id_part = f" (id={entry.id})" if entry.id else ""
            lines.append(f"- {entry.path}{id_part}: {entry.description or 'No description.'}")
        return "\n".join(lines)

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=True)
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(serialized.encode("utf-8")).hexdigest()


class WindowInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = ""
    wm_class: str = ""
    wm_class_instance: str | None = None
    pid: int | None = None
    app_id: str | None = None
    workspace: int | None = None
    workspace_name: str | None = None
    monitor: str | None = None
    monitor_index: int | None = None
    fullscreen: bool = False
    maximized: bool = False
    urgent: bool = False
    demands_attention: bool = False
    z_order: int | None = None
    geometry: dict[str, Any] | None = None


class ProviderState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    focused_window: WindowInfo | None = None
    open_windows: list[WindowInfo] = Field(default_factory=list)
    active_workspace: int | None = None
    active_workspace_name: str | None = None
    workspace_count: int | None = None
    screen_locked: bool = False
    idle_time_seconds: float | None = None
    timestamp: datetime
    screenshot_path: str | None = None


@dataclass(slots=True)
class ProviderSnapshot:
    revision: int
    state: ProviderState


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_path: str
    task_path: str | None = None


class PanelStateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = 0
    schema_version: int = PANEL_SCHEMA_VERSION
    kind: Literal[
        PANEL_KIND_CLASSIFIED,
        PANEL_KIND_UNCLASSIFIED,
        PANEL_KIND_DISCONNECTED,
        PANEL_KIND_PAUSED,
    ]
    top_level_id: str | None = None
    top_level_label: str | None = None
    icon_name: str
    path: str | None = None
    task_path: str | None = None
    task_id: str | None = None
    published_at: datetime
    catalog_hash: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "PanelStateRecord":
        if self.schema_version != PANEL_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported panel state schema version: {self.schema_version}"
            )
        if self.kind == PANEL_KIND_CLASSIFIED:
            if not self.top_level_id or not self.top_level_label or not self.path:
                raise ValueError(
                    "classified panel state must include top-level and path"
                )
            return self
        if self.path is not None or self.task_path is not None or self.task_id is not None:
            raise ValueError("non-classified panel state cannot include classified paths")
        if self.top_level_id is not None or self.top_level_label is not None:
            raise ValueError(
                "non-classified panel state cannot include top-level metadata"
            )
        return self

    @classmethod
    def classified(
        cls,
        *,
        revision: int,
        path: str,
        top_level_id: str,
        top_level_label: str,
        icon_name: str,
        published_at: datetime,
        catalog_hash: str | None,
        task_path: str | None = None,
        task_id: str | None = None,
    ) -> "PanelStateRecord":
        return cls(
            revision=revision,
            kind=PANEL_KIND_CLASSIFIED,
            top_level_id=top_level_id,
            top_level_label=top_level_label,
            icon_name=icon_name,
            path=path,
            task_path=task_path,
            task_id=task_id,
            published_at=published_at,
            catalog_hash=catalog_hash,
        )

    @classmethod
    def unclassified(
        cls,
        *,
        revision: int,
        published_at: datetime,
        catalog_hash: str | None,
    ) -> "PanelStateRecord":
        return cls(
            revision=revision,
            kind=PANEL_KIND_UNCLASSIFIED,
            top_level_id=None,
            top_level_label=None,
            icon_name=UNCLASSIFIED_ICON,
            path=None,
            published_at=published_at,
            catalog_hash=catalog_hash,
        )

    @classmethod
    def disconnected(
        cls,
        *,
        revision: int,
        published_at: datetime,
        catalog_hash: str | None = None,
    ) -> "PanelStateRecord":
        return cls(
            revision=revision,
            kind=PANEL_KIND_DISCONNECTED,
            top_level_id=None,
            top_level_label=None,
            icon_name=DISCONNECTED_ICON,
            path=None,
            published_at=published_at,
            catalog_hash=catalog_hash,
        )

    @classmethod
    def paused(
        cls,
        *,
        revision: int,
        published_at: datetime,
        catalog_hash: str | None = None,
    ) -> "PanelStateRecord":
        return cls(
            revision=revision,
            kind=PANEL_KIND_PAUSED,
            top_level_id=None,
            top_level_label=None,
            icon_name=PAUSED_ICON,
            path=None,
            published_at=published_at,
            catalog_hash=catalog_hash,
        )

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"revision"})

    def payload_json(self) -> str:
        return json.dumps(self.payload(), sort_keys=True)

    def same_value(self, other: "PanelStateRecord | None") -> bool:
        if other is None:
            return False
        left = self.model_dump(mode="json", exclude={"revision", "published_at"})
        right = other.model_dump(mode="json", exclude={"revision", "published_at"})
        return left == right


class DisplayRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    label: str
    icon_name: str | None = None
    seconds: float = 0.0
    is_selected: bool = False
    is_legacy: bool = False
    is_task: bool = False


class UIStateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = 0
    schema_version: int = PANEL_SCHEMA_VERSION
    kind: Literal[
        PANEL_KIND_CLASSIFIED,
        PANEL_KIND_UNCLASSIFIED,
        PANEL_KIND_DISCONNECTED,
        PANEL_KIND_PAUSED,
    ]
    top_level_id: str | None = None
    top_level_label: str | None = None
    icon_name: str
    path: str | None = None
    task_path: str | None = None
    task_id: str | None = None
    published_at: datetime
    catalog_hash: str | None = None
    tracking_enabled: bool = True
    display_label: str
    display_rows: list[DisplayRow] = Field(default_factory=list)

    @classmethod
    def from_panel_state(
        cls,
        panel_state: PanelStateRecord,
        *,
        tracking_enabled: bool,
        display_label: str,
        display_rows: list[DisplayRow],
    ) -> "UIStateRecord":
        return cls(
            revision=panel_state.revision,
            kind=panel_state.kind,
            top_level_id=panel_state.top_level_id,
            top_level_label=panel_state.top_level_label,
            icon_name=panel_state.icon_name,
            path=panel_state.path,
            task_path=panel_state.task_path,
            task_id=panel_state.task_id,
            published_at=panel_state.published_at,
            catalog_hash=panel_state.catalog_hash,
            tracking_enabled=tracking_enabled,
            display_label=display_label,
            display_rows=display_rows,
        )

    def to_panel_state(self) -> PanelStateRecord:
        return PanelStateRecord.model_validate(
            self.model_dump(
                mode="python",
                include={
                    "revision",
                    "schema_version",
                    "kind",
                    "top_level_id",
                    "top_level_label",
                    "icon_name",
                    "path",
                    "task_path",
                    "task_id",
                    "published_at",
                    "catalog_hash",
                },
            )
        )

    def payload_json(self) -> str:
        return self.model_dump_json(indent=2)


class SpanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    top_level: str
    task_path: str | None = None
    task_id: str | None = None
    started_at: datetime
    ended_at: datetime
    duration_seconds: float


@dataclass(slots=True)
class AppPaths:
    state_dir: Path
    raw_events_log: Path
    activity_log: Path
    debug_log: Path
    status_json: Path
    spans_log: Path
    tracking_json: Path
    task_pins_json: Path

    @classmethod
    def default(cls) -> "AppPaths":
        return cls.from_state_dir(STATE_DIR)

    @classmethod
    def from_state_dir(cls, state_dir: Path) -> "AppPaths":
        return cls(
            state_dir=state_dir,
            raw_events_log=state_dir / "raw-events.jsonl",
            activity_log=state_dir / "activity.jsonl",
            debug_log=state_dir / "debug.jsonl",
            status_json=state_dir / "status.json",
            spans_log=state_dir / "spans.jsonl",
            tracking_json=state_dir / "tracking.json",
            task_pins_json=state_dir / "task-pins.json",
        )


def utcnow() -> datetime:
    return datetime.now(tz=UTC)
