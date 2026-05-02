from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from json import dumps, loads
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

from ..models import SpanRecord
from .data import Period
from .theme import THEME_NAMES, get_theme
from .views import DailyView, OverviewView, StatsView, WeeklyView


class ViewMode(str, Enum):
    OVERVIEW = "overview"
    DAILY = "daily"
    WEEKLY = "weekly"
    STATS = "stats"


VIEW_LABELS = {
    ViewMode.OVERVIEW: "1 Overview",
    ViewMode.DAILY: "2 Daily",
    ViewMode.WEEKLY: "3 Weekly",
    ViewMode.STATS: "4 Stats",
}


class ViewTabs(Static):
    DEFAULT_CSS = """
    ViewTabs {
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """

    current_view: reactive[ViewMode] = reactive(ViewMode.DAILY)
    theme_name: reactive[str] = reactive("green")

    def render(self) -> Text:
        theme = get_theme(self.theme_name)
        text = Text()
        for i, mode in enumerate(ViewMode):
            if i > 0:
                text.append("  ")
            label = VIEW_LABELS[mode]
            if mode == self.current_view:
                text.append(f"[{label}]", style=f"bold {theme.accent}")
            else:
                text.append(f" {label} ", style="dim")
        return text

    def watch_current_view(self, view: ViewMode) -> None:
        self.refresh()

    def watch_theme_name(self, theme_name: str) -> None:
        self.refresh()


SETTINGS_PATH = Path.home() / ".config" / "waid" / "viewer.json"


def load_settings() -> dict[str, Any]:
    if SETTINGS_PATH.exists():
        try:
            return loads(SETTINGS_PATH.read_text())
        except Exception:
            pass
    return {}


def save_settings(settings: dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(dumps(settings, indent=2))


class StatsApp(App[None]):
    CSS = """
    StatsApp {
        background: $surface;
    }
    Container {
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("1", "view_overview", "Overview"),
        Binding("2", "view_daily", "Daily"),
        Binding("3", "view_weekly", "Weekly"),
        Binding("4", "view_stats", "Stats"),
        Binding("left", "nav_left", "Prev"),
        Binding("right", "nav_right", "Next"),
        Binding("t", "period_today", "Today"),
        Binding("w", "period_week", "Week"),
        Binding("m", "period_month", "Month"),
        Binding("y", "period_all", "All"),
        Binding("p", "cycle_theme", "Theme"),
        Binding("s", "toggle_sort", "Sort"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    current_view: reactive[ViewMode] = reactive(ViewMode.DAILY)
    theme_name: reactive[str] = reactive("green")
    theme_idx: reactive[int] = reactive(0)

    def __init__(
        self, spans: list[SpanRecord], start_view: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self._spans = spans
        self._start_view = start_view
        settings = load_settings()
        self.theme_name = settings.get("theme", "green")
        self.theme_idx = (
            THEME_NAMES.index(self.theme_name) if self.theme_name in THEME_NAMES else 0
        )

    def compose(self) -> ComposeResult:
        yield Header()
        yield ViewTabs()
        with Container():
            yield DailyView(spans=self._spans, id="view-daily")
            yield OverviewView(spans=self._spans, id="view-overview")
            yield WeeklyView(spans=self._spans, id="view-weekly")
            yield StatsView(spans=self._spans, id="view-stats")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(ViewTabs).theme_name = self.theme_name
        if self._start_view:
            try:
                self.current_view = ViewMode(self._start_view)
            except ValueError:
                pass
        self._show_view(self.current_view)

    def _show_view(self, view: ViewMode) -> None:
        views = {
            ViewMode.OVERVIEW: self.query_one("#view-overview", OverviewView),
            ViewMode.DAILY: self.query_one("#view-daily", DailyView),
            ViewMode.WEEKLY: self.query_one("#view-weekly", WeeklyView),
            ViewMode.STATS: self.query_one("#view-stats", StatsView),
        }
        for v in views.values():
            v.display = False
        views[view].display = True
        views[view].theme_name = self.theme_name

    def watch_current_view(self, view: ViewMode) -> None:
        self._show_view(view)
        tabs = self.query_one(ViewTabs)
        tabs.current_view = view

    def watch_theme_name(self, theme_name: str) -> None:
        try:
            self.query_one(ViewTabs).theme_name = theme_name
        except Exception:
            pass
        for view_id in ["view-overview", "view-daily", "view-weekly", "view-stats"]:
            try:
                view = self.query_one(f"#{view_id}")
                view.theme_name = theme_name
            except Exception:
                pass

    def action_view_overview(self) -> None:
        self.current_view = ViewMode.OVERVIEW

    def action_view_daily(self) -> None:
        self.current_view = ViewMode.DAILY

    def action_view_weekly(self) -> None:
        self.current_view = ViewMode.WEEKLY

    def action_view_stats(self) -> None:
        self.current_view = ViewMode.STATS

    def action_nav_left(self) -> None:
        if self.current_view == ViewMode.DAILY:
            view = self.query_one("#view-daily", DailyView)
            view.date = view.date - __import__("datetime").timedelta(days=1)
        elif self.current_view == ViewMode.WEEKLY:
            view = self.query_one("#view-weekly", WeeklyView)
            view.week_start = view.week_start - __import__("datetime").timedelta(
                weeks=1
            )
        elif self.current_view == ViewMode.OVERVIEW:
            view = self.query_one("#view-overview", OverviewView)
            view.year = view.year - 1

    def action_nav_right(self) -> None:
        if self.current_view == ViewMode.DAILY:
            view = self.query_one("#view-daily", DailyView)
            view.date = view.date + __import__("datetime").timedelta(days=1)
        elif self.current_view == ViewMode.WEEKLY:
            view = self.query_one("#view-weekly", WeeklyView)
            view.week_start = view.week_start + __import__("datetime").timedelta(
                weeks=1
            )
        elif self.current_view == ViewMode.OVERVIEW:
            view = self.query_one("#view-overview", OverviewView)
            view.year = view.year + 1

    def action_period_today(self) -> None:
        if self.current_view == ViewMode.STATS:
            view = self.query_one("#view-stats", StatsView)
            view.period = Period.TODAY

    def action_period_week(self) -> None:
        if self.current_view == ViewMode.STATS:
            view = self.query_one("#view-stats", StatsView)
            view.period = Period.WEEK

    def action_period_month(self) -> None:
        if self.current_view == ViewMode.STATS:
            view = self.query_one("#view-stats", StatsView)
            view.period = Period.MONTH

    def action_period_all(self) -> None:
        if self.current_view == ViewMode.STATS:
            view = self.query_one("#view-stats", StatsView)
            view.period = Period.ALL

    def action_cycle_theme(self) -> None:
        self.theme_idx = (self.theme_idx + 1) % len(THEME_NAMES)
        self.theme_name = THEME_NAMES[self.theme_idx]
        save_settings({"theme": self.theme_name})

    def action_toggle_sort(self) -> None:
        if self.current_view == ViewMode.STATS:
            view = self.query_one("#view-stats", StatsView)
            table = view.query_one("StatsTable")
            table.sort_by = "name" if table.sort_by == "time" else "time"

    def action_refresh(self) -> None:
        self.refresh()
