from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import time
from typing import Any

from .constants import DEBUG_ENV_VAR
from .storage import append_jsonl


def debug_enabled() -> bool:
    value = os.environ.get(DEBUG_ENV_VAR, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


class DebugLogger:
    def __init__(self, path: Path, *, enabled: bool) -> None:
        self.path = path
        self.enabled = enabled

    def log(self, event: str, **payload: Any) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        append_jsonl(
            self.path,
            {
                "ts": datetime.now(tz=UTC).isoformat(),
                "event": event,
                **payload,
            },
        )


def load_debug_entries(path: Path, *, lines: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in deque(handle, maxlen=max(1, lines)):
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = {"event": "malformed_debug_line", "raw": text}
            if isinstance(parsed, dict):
                entries.append(parsed)
    return entries


def follow_debug_entries(path: Path) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with path.open("r", encoding="utf-8") as handle:
        handle.seek(0, os.SEEK_END)
        while True:
            line = handle.readline()
            if not line:
                time.sleep(0.25)
                continue
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = {"event": "malformed_debug_line", "raw": text}
            if isinstance(parsed, dict):
                yield parsed


def format_debug_entry(entry: dict[str, Any]) -> str:
    timestamp = _format_timestamp(entry.get("ts"))
    event = str(entry.get("event", "unclassified"))

    if event == "provider_state":
        state = entry.get("state") or {}
        focused = state.get("focused_window") or {}
        title = focused.get("title") or "-"
        wm_class = focused.get("wm_class") or "-"
        previous = entry.get("previous_path") or "none"
        return (
            f"{timestamp} provider: title={title!r} app={wm_class} previous={previous}"
        )

    if event == "config_reload_start":
        catalog = entry.get("catalog") or []
        return f"{timestamp} config: reload started with {len(catalog)} current catalog entries"

    if event == "config_reload_complete":
        catalog = entry.get("catalog") or []
        return f"{timestamp} config: reload complete with {len(catalog)} catalog entries"

    if event == "config_reload_failed":
        return f"{timestamp} config: reload failed: {entry.get('error', '-')}"

    if event == "classifier_attempt":
        previous = entry.get("previous_path") or "none"
        attempt = entry.get("attempt", 0)
        allowed = entry.get("activity_outputs") or []
        return f"{timestamp} classifier: attempt {attempt}, previous={previous}, activities={len(allowed)}"

    if event == "classifier_result":
        attempt = entry.get("attempt", 0)
        result = entry.get("result") or "<empty>"
        return f"{timestamp} classifier: attempt {attempt} returned {result}"

    if event == "classifier_fallback":
        fallback = entry.get("fallback") or "unclassified"
        invalid = entry.get("last_invalid") or "<empty>"
        return f"{timestamp} classifier: falling back to {fallback} after invalid result {invalid}"

    if event == "classifier_cache_store":
        return f"{timestamp} classifier: cached result {entry.get('selected_path', 'unclassified')}"

    if event == "classifier_cache_hit":
        return f"{timestamp} classifier: cache hit -> {entry.get('selected_path', 'unclassified')}"

    if event == "activity_changed":
        previous = entry.get("previous_path") or "none"
        selected = entry.get("selected_path") or "unclassified"
        return f"{timestamp} activity: {previous} -> {selected}"

    if event == "activity_unchanged":
        return f"{timestamp} activity: unchanged at {entry.get('selected_path', 'unclassified')}"

    if event == "action_dispatch":
        calls = entry.get("calls") or []
        return f"{timestamp} actions: dispatching {len(calls)} call(s) for {entry.get('path', 'unclassified')}"

    if event == "tool_run":
        command = " ".join(entry.get("command") or [])
        args = " ".join(entry.get("args") or [])
        timeout = entry.get("timeout_seconds")
        suffix = f" {args}".rstrip()
        return f"{timestamp} tool: run {command}{suffix} (timeout={timeout}s)"

    if event == "tool_result":
        command = " ".join(entry.get("command") or [])
        args = " ".join(entry.get("args") or [])
        returncode = entry.get("returncode", 0)
        stdout = _shorten(entry.get("stdout"))
        stderr = _shorten(entry.get("stderr"))
        summary = stdout or stderr or "-"
        suffix = f" {args}".rstrip()
        return f"{timestamp} tool: result {command}{suffix} exit={returncode} output={summary}"

    if event == "tool_timeout":
        command = " ".join(entry.get("command") or [])
        args = " ".join(entry.get("args") or [])
        suffix = f" {args}".rstrip()
        return f"{timestamp} tool: timeout {command}{suffix}"

    if event == "llm_request":
        model = entry.get("model") or "-"
        json_mode = "json" if entry.get("json_mode") else "text"
        return f"{timestamp} llm: request model={model} mode={json_mode}"

    if event == "llm_response":
        model = entry.get("model") or "-"
        content = _shorten(entry.get("content"))
        return f"{timestamp} llm: response model={model} content={content}"

    if event == "llm_response_raw":
        model = entry.get("model") or "-"
        body = _shorten(entry.get("body"))
        return f"{timestamp} llm: raw response model={model} body={body}"

    if event == "llm_error":
        model = entry.get("model") or "-"
        error = _shorten(entry.get("error"))
        body = _shorten(entry.get("body"))
        if body:
            return f"{timestamp} llm: error model={model} error={error} body={body}"
        return f"{timestamp} llm: error model={model} error={error}"

    if event == "malformed_debug_line":
        return f"{timestamp} debug: malformed line {_shorten(entry.get('raw'))}"

    extra = ", ".join(
        f"{key}={_shorten(value)}"
        for key, value in sorted(entry.items())
        if key not in {"ts", "event"}
    )
    return f"{timestamp} {event}: {extra}"


def _format_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "---- --:--:--"
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return value
    return stamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _shorten(value: Any, *, limit: int = 140) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip().replace("\n", " | ")
    else:
        text = json.dumps(value, ensure_ascii=True, sort_keys=True)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
