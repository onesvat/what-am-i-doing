from __future__ import annotations

from datetime import datetime
from typing import Any

from rich.text import Text
from textual.widget import Widget
from textual.widgets import Static

from ..data import format_duration
from ..theme import ColorTheme, get_theme


class HourBlock(Widget):
    DEFAULT_CSS = """
    HourBlock {
        height: 1;
        padding: 0 1;
        margin: 0;
    }
    HourBlock.empty {
        color: $text-muted;
    }
    HourBlock.filled {
        color: $text;
    }
    """

    def __init__(
        self,
        hour: int,
        spans: list[Any],
        theme: ColorTheme | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hour = hour
        self._spans = spans
        self._theme = theme or get_theme("green")

    def render(self) -> Text:
        hour_str = f"{self.hour:02d}:00"
        if not self._spans:
            self.add_class("empty")
            self.remove_class("filled")
            return Text(hour_str + "  —", style="dim")

        self.add_class("filled")
        self.remove_class("empty")

        total_seconds = sum(s.duration_seconds for s in self._spans)
        primary = max(self._spans, key=lambda s: s.duration_seconds)
        label = primary.path if "/" in primary.path else primary.top_level
        dur = format_duration(total_seconds)
        return Text(f"{hour_str}  {label} ({dur})")
