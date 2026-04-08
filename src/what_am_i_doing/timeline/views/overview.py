from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..data import category_totals, format_duration, contribution_data, Period
from ..theme import ColorTheme, get_theme
from ..widgets import ContributionGraph


class OverviewStats(Static):
    DEFAULT_CSS = """
    OverviewStats {
        height: auto;
        padding: 1;
    }
    """

    year: reactive[int] = reactive(lambda: datetime.now(tz=UTC).year)

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def watch_year(self, year: int) -> None:
        self._refresh()

    def _refresh(self) -> None:
        data = contribution_data(self._spans, self.year)
        total_seconds = sum(data.values())
        active_days = len(data)
        max_day_seconds = max(data.values()) if data else 0
        streak = self._calculate_streak(data)

        total_hours = total_seconds / 3600
        max_hours = max_day_seconds / 3600

        lines: list[str] = []
        lines.append(f"\n{self.year} Overview")
        lines.append("")
        lines.append(
            f"  Total Time:      {format_duration(total_seconds)} ({total_hours:.1f}h)"
        )
        lines.append(f"  Active Days:     {active_days}")
        lines.append(f"  Current Streak:  {streak} days")
        lines.append(
            f"  Best Day:        {format_duration(max_day_seconds)} ({max_hours:.1f}h)"
        )
        lines.append("")
        self.update("\n".join(lines))

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
        padding: 1;
    }
    """

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def on_mount(self) -> None:
        totals = category_totals(self._spans, Period.WEEK)
        by_top = totals["by_top"]
        total = sum(by_top.values())
        lines: list[str] = []
        lines.append("Top Categories This Week")
        lines.append("")
        for top, seconds in list(
            sorted(by_top.items(), key=lambda x: x[1], reverse=True)
        )[:5]:
            dur = format_duration(seconds)
            pct = (seconds / total * 100) if total > 0 else 0
            lines.append(f"  {top:<20} {dur:>8} ({pct:.0f}%)")
        self.update("\n".join(lines))


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
        yield Static("\nPress ←/→ to change year, p to cycle theme\n")
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

    def on_mount(self) -> None:
        self.query_one(OverviewStats).year = self.year
        self.query_one(ContributionGraph).year = self.year
