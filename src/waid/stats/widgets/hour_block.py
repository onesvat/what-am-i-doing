from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.widget import Widget

from ..data import format_duration
from ..theme import ColorTheme, get_theme, intensity_level, level_color


class HourBlock(Widget):
    DEFAULT_CSS = """
    HourBlock {
        height: 1;
        padding: 0 1;
        margin: 0;
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
            text = Text()
            text.append(hour_str, style="dim")
            return text

        total_seconds = sum(s.duration_seconds for s in self._spans)
        primary = max(self._spans, key=lambda s: s.duration_seconds)
        label = primary.path if "/" in primary.path else primary.top_level
        dur = format_duration(total_seconds)

        max_seconds = 3600.0
        bar_width = 12
        level = intensity_level(total_seconds, max_seconds)
        color = level_color(self._theme, level)
        filled = max(1, int(total_seconds / max_seconds * bar_width))
        filled = min(filled, bar_width)

        text = Text()
        text.append(hour_str + " ", style="dim")
        text.append("█" * filled, style=color)
        text.append("░" * (bar_width - filled), style="dim")
        text.append(f" {label[:24]}", style="bold")
        text.append(f" {dur}", style="dim")
        return text
