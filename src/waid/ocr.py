from __future__ import annotations

from pathlib import Path
from typing import Any

_engine: Any = None


def _get_engine() -> Any:
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def screenshot_to_text(path: Path) -> str:
    try:
        engine = _get_engine()
        result, _ = engine(str(path))
        if not result:
            return ""
        return "\n".join(item[1] for item in result if item[1]).strip()
    except Exception:
        return ""
