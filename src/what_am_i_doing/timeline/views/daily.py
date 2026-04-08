from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Static

from ..data import daily_summary, format_duration, spans_by_hour
from ..theme import ColorTheme, get_theme
from ..widgets import HourBlock


class DateChanged(Message):
    def __init__(self, date: datetime) -> None:
        super().__init__()
        self.date = date


class DateHeader(Widget):
    DEFAULT_CSS = """
    DateHeader {
        height: 3;
        padding: 1;
        background: $surface;
    }
    DateHeader Button {
        width: 8;
    }
    """

    date: reactive[datetime] = reactive(lambda: datetime.now(tz=UTC))

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Button("◀ Prev", id="prev-day")
            yield Static("", id="date-display")
            yield Button("Next ▶", id="next-day")

    def watch_date(self, date: datetime) -> None:
        display = self.query_one("#date-display", Static)
        weekday = date.strftime("%A")
        formatted = date.strftime("%B %d, %Y")
        summary = daily_summary(self._spans, date)
        dur = format_duration(summary["total_seconds"])
        display.update(Text(f"{weekday}, {formatted}  —  Total: {dur}"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prev-day":
            self.date = self.date - timedelta(days=1)
            self.post_message(DateChanged(self.date))
        elif event.button.id == "next-day":
            self.date = self.date + timedelta(days=1)
            self.post_message(DateChanged(self.date))


class DailyTimeline(Widget):
    DEFAULT_CSS = """
    DailyTimeline {
        height: auto;
        padding: 1;
    }
    """

    date: reactive[datetime] = reactive(lambda: datetime.now(tz=UTC))
    theme_name: reactive[str] = reactive("green")

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def compose(self) -> ComposeResult:
        with Vertical():
            for hour in range(24):
                yield HourBlock(hour=hour, spans=[], id=f"hour-{hour}")

    def watch_date(self, date: datetime) -> None:
        self._refresh_blocks()

    def watch_theme_name(self, theme_name: str) -> None:
        self._refresh_blocks()

    def _refresh_blocks(self) -> None:
        theme = get_theme(self.theme_name)
        by_hour = spans_by_hour(self._spans, self.date)
        for hour in range(24):
            try:
                block = self.query_one(f"#hour-{hour}", HourBlock)
            except Exception:
                continue
            block._spans = by_hour.get(hour, [])
            block._theme = theme
            block.refresh()

    def on_mount(self) -> None:
        self._refresh_blocks()


class CategorySummary(Static):
    DEFAULT_CSS = """
    CategorySummary {
        height: auto;
        padding: 1;
        background: $surface;
    }
    """

    date: reactive[datetime] = reactive(lambda: datetime.now(tz=UTC))

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def watch_date(self, date: datetime) -> None:
        summary = daily_summary(self._spans, date)
        by_path = summary["by_path"]
        total = summary["total_seconds"]
        lines: list[str] = []
        lines.append(f"Active: {summary['active_hours']} hours")
        lines.append("")
        for path, seconds in list(by_path.items())[:10]:
            dur = format_duration(seconds)
            pct = (seconds / total * 100) if total > 0 else 0
            lines.append(f"  {path:<30} {dur:>6} ({pct:.0f}%)")
        self.update("\n".join(lines))


class DailyView(Widget):
    DEFAULT_CSS = """
    DailyView {
        height: 100%;
    }
    """

    date: reactive[datetime] = reactive(lambda: datetime.now(tz=UTC))
    theme_name: reactive[str] = reactive("green")

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def compose(self) -> ComposeResult:
        yield DateHeader(spans=self._spans)
        yield DailyTimeline(spans=self._spans)
        yield CategorySummary(spans=self._spans)

    def on_mount(self) -> None:
        self._sync_children()

    def watch_date(self, date: datetime) -> None:
        self._sync_children()

    def watch_theme_name(self, theme_name: str) -> None:
        self._sync_children()

    def _sync_children(self) -> None:
        header = self.query_one(DateHeader)
        header.date = self.date
        timeline = self.query_one(DailyTimeline)
        timeline.date = self.date
        timeline.theme_name = self.theme_name
        summary = self.query_one(CategorySummary)
        summary.date = self.date

    def on_date_changed(self, event: DateChanged) -> None:
        self.date = event.date
