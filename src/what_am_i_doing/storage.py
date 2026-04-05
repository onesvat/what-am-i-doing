from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .models import AppPaths, SpanRecord, StatusRecord, Taxonomy


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


def load_status(path: Path) -> StatusRecord | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return StatusRecord.model_validate_json(handle.read())


def save_status(path: Path, status: StatusRecord) -> None:
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
