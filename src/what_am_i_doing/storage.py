from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .constants import PANEL_KIND_CLASSIFIED, PANEL_KIND_UNCLASSIFIED
from .models import (
    AppPaths,
    PanelStateRecord,
    SpanRecord,
    Taxonomy,
    utcnow,
)


def ensure_state_dir(paths: AppPaths) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def load_taxonomy(path: Path) -> Taxonomy | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return Taxonomy.model_validate_json(handle.read())


def save_taxonomy(path: Path, taxonomy: Taxonomy) -> None:
    path.write_text(taxonomy.model_dump_json(indent=2), encoding="utf-8")


def load_status(path: Path) -> PanelStateRecord | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        raw = json.loads(handle.read())
    if "kind" in raw:
        return PanelStateRecord.model_validate(raw)
    updated_at = raw.get("updated_at")
    published_at = (
        parse_timestamp(updated_at) if isinstance(updated_at, str) else utcnow()
    )
    current_path = raw.get("current_path")
    taxonomy_hash = raw.get("taxonomy_hash")
    if current_path and current_path != "unknown":
        top_level = raw.get("top_level") or str(current_path).split("/", 1)[0]
        return PanelStateRecord.classified(
            revision=int(raw.get("revision", 0)),
            path=current_path,
            top_level_id=top_level,
            top_level_label=top_level,
            icon_name=raw.get("icon") or "applications-system-symbolic",
            published_at=published_at,
            taxonomy_hash=taxonomy_hash or "legacy",
        )
    return PanelStateRecord.unclassified(
        revision=int(raw.get("revision", 0)),
        published_at=published_at,
        taxonomy_hash=taxonomy_hash,
    )


def save_status(path: Path, status: PanelStateRecord) -> None:
    path.write_text(status.model_dump_json(indent=2), encoding="utf-8")


def save_span(path: Path, span: SpanRecord) -> None:
    append_jsonl(path, span.model_dump(mode="json"))


def load_spans(path: Path) -> list[SpanRecord]:
    if not path.exists():
        return []
    spans: list[SpanRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            spans.append(SpanRecord.model_validate_json(line))
    return spans


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)
