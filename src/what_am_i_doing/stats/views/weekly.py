from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..data import format_duration, spans_by_day, weekly_summary
from ..theme import ColorTheme, get_theme


class WeekChanged(Message):
    def __init__(self, week_start: datetime) -> None:
        super().__init__()
        self.week_start = week_start


class WeekHeader(Static):
    DEFAULT_CSS = """
    WeekHeader {
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """

    week_start: reactive[datetime] = reactive(lambda: datetime.now(tz=UTC))

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def render(self) -> Text:
        text = Text()
        text.append("‹ ", style="dim")
        week_end = self.week_start + timedelta(days=6)
        start_str = self.week_start.strftime("%b %d")
        end_str = week_end.strftime("%b %d, %Y")
        summary = weekly_summary(self._spans, self.week_start)
        dur = format_duration(summary["total_seconds"])
        text.append(f"{start_str} – {end_str}", style="bold")
        text.append("  —  Total: ", style="dim")
        text.append(dur, style="bold")
        text.append(" ›", style="dim")
        return text

    def watch_week_start(self, week_start: datetime) -> None:
        self.refresh()


class DayColumn(Widget):
    DEFAULT_CSS = """
    DayColumn {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(
        self, date: datetime, spans: list[Any], theme: ColorTheme, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self._date = date
        self._spans = spans
        self._theme = theme

    def compose(self) -> ComposeResult:
        theme = self._theme
        day_name = self._date.strftime("%a")
        day_num = self._date.strftime("%d")
        header = Text()
        header.append(f"{day_name} ", style="dim")
        header.append(day_num, style="bold")
        yield Static(header)

        totals: dict[str, float] = {}
        for span in self._spans:
            totals[span.top_level] = (
                totals.get(span.top_level, 0.0) + span.duration_seconds
            )

        for top, seconds in sorted(totals.items(), key=lambda x: x[1], reverse=True)[
            :6
        ]:
            dur = format_duration(seconds)
            text = Text()
            text.append("● ", style=f"{theme.accent}")
            text.append(f"{top[:10]:10}", style="bold")
            text.append(f" {dur:>5}", style="dim")
            yield Static(text)


class WeeklyGrid(Widget):
    DEFAULT_CSS = """
    WeeklyGrid {
        height: auto;
        padding: 0 1;
    }
    """

    week_start: reactive[datetime] = reactive(lambda: datetime.now(tz=UTC))
    theme_name: reactive[str] = reactive("green")

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def compose(self) -> ComposeResult:
        with Horizontal():
            for offset in range(7):
                day = datetime.now(tz=UTC) + timedelta(days=offset)
                yield DayColumn(date=day, spans=[], theme=get_theme("green"))

    def watch_week_start(self, week_start: datetime) -> None:
        self._refresh_columns()

    def watch_theme_name(self, theme_name: str) -> None:
        self._refresh_columns()

    def _refresh_columns(self) -> None:
        theme = get_theme(self.theme_name)
        by_day = spans_by_day(self._spans, self.week_start)
        columns = self.query(DayColumn)
        for idx, col in enumerate(columns):
            day = self.week_start + timedelta(days=idx)
            col._date = day
            col._spans = by_day.get(day, [])
            col._theme = theme
            col.refresh(recompose=True)

    def on_mount(self) -> None:
        self._refresh_columns()


class WeeklyView(Widget):
    DEFAULT_CSS = """
    WeeklyView {
        height: 100%;
    }
    """

    week_start: reactive[datetime] = reactive(lambda: datetime.now(tz=UTC))
    theme_name: reactive[str] = reactive("green")

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def compose(self) -> ComposeResult:
        yield WeekHeader(spans=self._spans)
        yield WeeklyGrid(spans=self._spans)

    def watch_week_start(self, week_start: datetime) -> None:
        header = self.query_one(WeekHeader)
        header.week_start = week_start
        grid = self.query_one(WeeklyGrid)
        grid.week_start = week_start

    def watch_theme_name(self, theme_name: str) -> None:
        grid = self.query_one(WeeklyGrid)
        grid.theme_name = theme_name

    def on_mount(self) -> None:
        now = datetime.now(tz=UTC)
        weekday = now.weekday()
        self.week_start = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=weekday)

    def on_week_changed(self, event: WeekChanged) -> None:
        self.week_start = event.week_start
