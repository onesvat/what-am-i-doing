from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .constants import FALLBACK_CATEGORY, STATE_DIR


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    args: list[str] = Field(default_factory=list)


class TaxonomyNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    icon: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    children: list["TaxonomyNode"] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_name_and_children(self) -> "TaxonomyNode":
        if not self.name or "/" in self.name:
            raise ValueError("category names must be non-empty and cannot contain '/'")
        names = [child.name for child in self.children]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate child names under {self.name}")
        return self


class Taxonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[TaxonomyNode]

    @model_validator(mode="after")
    def validate_unique_roots(self) -> "Taxonomy":
        names = [node.name for node in self.categories]
        if len(names) != len(set(names)):
            raise ValueError("duplicate top-level categories")
        return self

    def ensure_fallback(self, fallback: str = FALLBACK_CATEGORY) -> "Taxonomy":
        if fallback in self.allowed_paths():
            return self
        categories = list(self.categories)
        categories.append(
            TaxonomyNode(
                name=fallback,
                description="Reserved fallback category.",
                icon="help-about-symbolic",
                tool_calls=[],
                children=[],
            )
        )
        return Taxonomy(categories=categories)

    def allowed_paths(self) -> set[str]:
        result: set[str] = set()
        for node in self.categories:
            result.add(node.name)
            for child in node.children:
                result.add(f"{node.name}/{child.name}")
        return result

    def top_level(self, path: str) -> str:
        return path.split("/", 1)[0]

    def node_for_path(self, path: str) -> tuple[TaxonomyNode, TaxonomyNode | None]:
        top, _, child = path.partition("/")
        for node in self.categories:
            if node.name != top:
                continue
            if not child:
                return node, None
            for subnode in node.children:
                if subnode.name == child:
                    return node, subnode
        raise KeyError(path)

    def tools_for_path(self, path: str) -> list[ToolCall]:
        top, child = self.node_for_path(path)
        calls = list(top.tool_calls)
        if child is not None:
            calls.extend(child.tool_calls)
        return calls

    def describe(self) -> str:
        lines: list[str] = []
        for node in self.categories:
            lines.append(f"- {node.name}: {node.description}")
            for child in node.children:
                lines.append(f"  - {node.name}/{child.name}: {child.description}")
        return "\n".join(lines)

    def validate_action_tool_refs(self, known_tools: set[str]) -> None:
        for node in self.categories:
            self._validate_node_tools(node, known_tools)

    def _validate_node_tools(self, node: TaxonomyNode, known_tools: set[str]) -> None:
        for call in node.tool_calls:
            if call.tool not in known_tools:
                raise ValueError(f"unknown action tool in taxonomy: {call.tool}")
        for child in node.children:
            self._validate_node_tools(child, known_tools)

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
    workspace: int | None = None
    workspace_name: str | None = None
    monitor: str | None = None
    monitor_index: int | None = None
    fullscreen: bool = False
    maximized: bool = False
    geometry: dict[str, Any] | None = None


class ProviderState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    focused_window: WindowInfo | None = None
    open_windows: list[WindowInfo] = Field(default_factory=list)
    active_workspace: int | None = None
    workspace_count: int | None = None
    screen_locked: bool = False
    timestamp: datetime


class StatusRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_path: str
    top_level: str
    icon: str | None = None
    updated_at: datetime
    taxonomy_hash: str


class SpanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    top_level: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float


@dataclass(slots=True)
class AppPaths:
    state_dir: Path
    raw_events_log: Path
    activity_log: Path
    debug_log: Path
    taxonomy_json: Path
    status_json: Path
    spans_log: Path

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
            taxonomy_json=state_dir / "taxonomy.json",
            status_json=state_dir / "status.json",
            spans_log=state_dir / "spans.jsonl",
        )


def utcnow() -> datetime:
    return datetime.now(tz=UTC)
