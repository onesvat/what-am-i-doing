from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
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
