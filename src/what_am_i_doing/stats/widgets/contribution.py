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

from ..data import contribution_data
from ..theme import ColorTheme, get_theme, intensity_level, level_color


class DayClicked(Message):
    def __init__(self, date: datetime) -> None:
        super().__init__()
        self.date = date


class ContributionDay(Widget):
    DEFAULT_CSS = """
    ContributionDay {
        width: 2;
        height: 1;
        padding: 0;
        margin: 0;
    }
    """

    date: reactive[datetime | None] = reactive(None)
    seconds: reactive[float] = reactive(0.0)
    max_seconds: reactive[float] = reactive(3600 * 8)
    theme: reactive[ColorTheme] = reactive(lambda: get_theme("green"))

    def __init__(
        self,
        date: datetime | None = None,
        seconds: float = 0.0,
        max_seconds: float = 3600 * 8,
        theme: ColorTheme | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.date = date
        self.seconds = seconds
        self.max_seconds = max_seconds
        self.theme = theme or get_theme("green")

    def render(self) -> Text:
        level = intensity_level(self.seconds, self.max_seconds)
        color = level_color(self.theme, level)
        return Text("█", style=f"on {color}")

    def on_click(self) -> None:
        if self.date:
            self.post_message(DayClicked(self.date))


class ContributionWeek(Widget):
    DEFAULT_CSS = """
    ContributionWeek {
        width: 2;
        height: 7;
        padding: 0;
        margin-right: 0;
    }
    """

    def __init__(
        self,
        week_start: datetime,
        data: dict[datetime, float],
        max_seconds: float,
        theme: ColorTheme,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._week_start = week_start
        self._data = data
        self._max_seconds = max_seconds
        self._theme = theme

    def compose(self) -> ComposeResult:
        for day_offset in range(7):
            day = self._week_start + timedelta(days=day_offset)
            seconds = self._data.get(day, 0.0)
            yield ContributionDay(
                date=day,
                seconds=seconds,
                max_seconds=self._max_seconds,
                theme=self._theme,
            )


class ContributionGraph(Widget):
    DEFAULT_CSS = """
    ContributionGraph {
        height: auto;
        padding: 0 1;
    }
    ContributionGraph Horizontal {
        height: auto;
    }
    """

    year: reactive[int] = reactive(lambda: datetime.now(tz=UTC).year)
    theme_name: reactive[str] = reactive("green")

    def __init__(
        self, spans: list[Any], year: int | None = None, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self._spans = spans
        self.year = year or datetime.now(tz=UTC).year

    def compose(self) -> ComposeResult:
        theme = get_theme(self.theme_name)
        data = contribution_data(self._spans, self.year)
        max_seconds = max(data.values()) if data else 3600 * 8

        year_start = datetime(self.year, 1, 1, tzinfo=UTC)
        first_weekday = year_start.weekday()
        weeks: list[datetime] = []
        current = year_start - timedelta(days=first_weekday)
        while current.year <= self.year or (
            current.year == self.year + 1 and current.month == 1
        ):
            weeks.append(current)
            current += timedelta(weeks=1)

        with Horizontal():
            for week_start in weeks[:53]:
                yield ContributionWeek(
                    week_start=week_start,
                    data=data,
                    max_seconds=max_seconds,
                    theme=theme,
                )

    def watch_theme_name(self, theme_name: str) -> None:
        self.refresh()


class ContributionHeader(Widget):
    DEFAULT_CSS = """
    ContributionHeader {
        height: 1;
        padding: 0;
        margin-bottom: 1;
    }
    """

    def render(self) -> Text:
        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        text = Text()
        for i, month in enumerate(months):
            text.append(f"{month:4}")
        return text
