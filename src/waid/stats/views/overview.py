from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..data import category_totals, format_duration, contribution_data, Period
from ..theme import get_theme
from ..widgets import ContributionGraph


class OverviewStats(Static):
    DEFAULT_CSS = """
    OverviewStats {
        height: auto;
        padding: 0 1;
    }
    """

    year: reactive[int] = reactive(lambda: datetime.now(tz=UTC).year)
    theme_name: reactive[str] = reactive("green")

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def watch_year(self, year: int) -> None:
        self._refresh()

    def watch_theme_name(self, theme_name: str) -> None:
        self._refresh()

    def _refresh(self) -> None:
        theme = get_theme(self.theme_name)
        data = contribution_data(self._spans, self.year)
        total_seconds = sum(data.values())
        active_days = len(data)
        max_day_seconds = max(data.values()) if data else 0
        streak = self._calculate_streak(data)

        total_hours = total_seconds / 3600
        max_hours = max_day_seconds / 3600

        text = Text()
        text.append(f"{self.year} Overview\n", style="bold")

        text.append("Total Time:      ", style="dim")
        text.append(f"{format_duration(total_seconds)} ({total_hours:.1f}h)\n", style=f"bold {theme.accent}")

        text.append("Active Days:     ", style="dim")
        text.append(f"{active_days}\n", style=f"bold {theme.accent}")

        text.append("Current Streak:  ", style="dim")
        text.append(f"{streak} days\n", style=f"bold {theme.accent}")

        text.append("Best Day:        ", style="dim")
        text.append(f"{format_duration(max_day_seconds)} ({max_hours:.1f}h)\n", style=f"bold {theme.accent}")

        self.update(text)

    def _calculate_streak(self, data: dict[datetime, float]) -> int:
        if not data:
            return 0
        today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        streak = 0
        current = today
        while data.get(current, 0) > 0:
            streak += 1
            current -= __import__("datetime").timedelta(days=1)
        return streak

    def on_mount(self) -> None:
        self._refresh()


class TopCategories(Static):
    DEFAULT_CSS = """
    TopCategories {
        height: auto;
        padding: 0 1;
    }
    """

    theme_name: reactive[str] = reactive("green")

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def _refresh(self) -> None:
        theme = get_theme(self.theme_name)
        totals = category_totals(self._spans, Period.WEEK)
        by_top = totals["by_top"]
        total = sum(by_top.values())

        items = sorted(by_top.items(), key=lambda x: x[1], reverse=True)[:5]
        max_seconds = items[0][1] if items else 1
        bar_width = 20

        text = Text()
        text.append("Top Categories This Week\n", style="bold")

        for top, seconds in items:
            dur = format_duration(seconds)
            pct = (seconds / total * 100) if total > 0 else 0
            filled = max(1, int(seconds / max_seconds * bar_width))
            bar = "█" * filled + "░" * (bar_width - filled)

            text.append(f"  {top:<20}", style=f"bold {theme.accent}")
            text.append(f" {dur:>8}", style="bold")
            text.append(f" ({pct:.0f}%)\n", style="dim")
            text.append(f"  {bar}\n", style=f"{theme.levels[2]}")

        self.update(text)

    def watch_theme_name(self, theme_name: str) -> None:
        self._refresh()

    def on_mount(self) -> None:
        self._refresh()


class OverviewView(Widget):
    DEFAULT_CSS = """
    OverviewView {
        height: 100%;
    }
    """

    year: reactive[int] = reactive(lambda: datetime.now(tz=UTC).year)
    theme_name: reactive[str] = reactive("green")

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def compose(self) -> ComposeResult:
        yield OverviewStats(spans=self._spans)
        yield ContributionGraph(spans=self._spans)
        yield TopCategories(spans=self._spans)

    def watch_year(self, year: int) -> None:
        stats = self.query_one(OverviewStats)
        stats.year = year
        graph = self.query_one(ContributionGraph)
        graph.year = year

    def watch_theme_name(self, theme_name: str) -> None:
        graph = self.query_one(ContributionGraph)
        graph.theme_name = theme_name
        try:
            self.query_one(OverviewStats).theme_name = theme_name
            self.query_one(TopCategories).theme_name = theme_name
        except Exception:
            pass

    def on_mount(self) -> None:
        self.query_one(OverviewStats).year = self.year
        self.query_one(ContributionGraph).year = self.year
