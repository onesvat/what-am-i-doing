from __future__ import annotations

from datetime import datetime
import json
import shutil
from pathlib import Path
from typing import Any

from .constants import LEGACY_CONFIG_DIR, LEGACY_STATE_DIR, PANEL_KIND_CLASSIFIED, UNKNOWN_PATH
from .models import AppPaths, PanelStateRecord, SpanRecord, UIStateRecord, utcnow


def ensure_state_dir(paths: AppPaths) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def load_ui_state(path: Path) -> UIStateRecord | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        raw = json.loads(handle.read())
    if not isinstance(raw, dict):
        return None
    raw = _normalize_catalog_keys(raw)
    if "display_rows" in raw or "display_label" in raw or "tracking_enabled" in raw:
        return UIStateRecord.model_validate(raw)

    panel_state = _panel_state_from_raw(raw)
    if panel_state is None:
        return None
    return UIStateRecord.from_panel_state(
        panel_state,
        tracking_enabled=True,
        display_label=panel_state.path or panel_state.kind,
        display_rows=[],
    )


def save_ui_state(path: Path, ui_state: UIStateRecord) -> None:
    path.write_text(ui_state.payload_json(), encoding="utf-8")


def load_status(path: Path) -> PanelStateRecord | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        raw = json.loads(handle.read())
    if not isinstance(raw, dict):
        return None
    raw = _normalize_catalog_keys(raw)
    if "display_rows" in raw or "display_label" in raw or "tracking_enabled" in raw:
        return UIStateRecord.model_validate(raw).to_panel_state()
    return _panel_state_from_raw(raw)


def _normalize_catalog_keys(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(raw)
    if "catalog_hash" not in normalized and "choices_hash" in normalized:
        normalized["catalog_hash"] = normalized["choices_hash"]
    return normalized


def _panel_state_from_raw(raw: dict[str, Any]) -> PanelStateRecord | None:
    if "kind" in raw:
        return PanelStateRecord.model_validate(raw)

    updated_at = raw.get("updated_at")
    published_at = (
        parse_timestamp(updated_at) if isinstance(updated_at, str) else utcnow()
    )
    current_path = raw.get("current_path")
    task_path = raw.get("task_path")
    catalog_hash = raw.get("catalog_hash")
    if catalog_hash is None and "choices_hash" in raw:
        catalog_hash = raw.get("choices_hash")
    if current_path and current_path != UNKNOWN_PATH:
        top_level = raw.get("top_level") or str(current_path).split("/", 1)[0]
        return PanelStateRecord.classified(
            revision=int(raw.get("revision", 0)),
            path=str(current_path),
            task_path=str(task_path) if isinstance(task_path, str) and task_path else None,
            top_level_id=str(top_level),
            top_level_label=str(top_level),
            icon_name=raw.get("icon") or "applications-system-symbolic",
            published_at=published_at,
            catalog_hash=catalog_hash or "legacy",
        )
    return PanelStateRecord.unclassified(
        revision=int(raw.get("revision", 0)),
        published_at=published_at,
        catalog_hash=catalog_hash,
    )


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


def load_tracking(path: Path) -> bool:
    if not path.exists():
        return True
    with path.open("r", encoding="utf-8") as handle:
        raw = json.loads(handle.read())
    return bool(raw.get("enabled", True))


def save_tracking(path: Path, enabled: bool) -> None:
    path.write_text(json.dumps({"enabled": enabled}, indent=2), encoding="utf-8")


def load_task_pins(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        raw = json.loads(handle.read())
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}


def save_task_pins(path: Path, pins: dict[str, str]) -> None:
    path.write_text(json.dumps(pins, indent=2, sort_keys=True), encoding="utf-8")


def migrate_legacy_dirs() -> None:
    from .constants import WAID_DIR

    if WAID_DIR.exists():
        return

    migrated = False

    if LEGACY_CONFIG_DIR.exists():
        for item in LEGACY_CONFIG_DIR.iterdir():
            dest = WAID_DIR / item.name
            if not dest.exists():
                WAID_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
                migrated = True

    if LEGACY_STATE_DIR.exists():
        dest_state = WAID_DIR / "state"
        dest_state.mkdir(parents=True, exist_ok=True)
        for item in LEGACY_STATE_DIR.iterdir():
            dest = dest_state / item.name
            if not dest.exists():
                shutil.copy2(item, dest)
                migrated = True
