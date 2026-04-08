from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from json import dumps, loads
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Static

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
        padding: 1;
        background: $surface;
    }
    ViewTabs Button {
        width: auto;
        min-width: 10;
        margin-right: 1;
    }
    ViewTabs Button.active {
        background: $accent;
        color: $text;
    }
    """

    current_view: reactive[ViewMode] = reactive(ViewMode.DAILY)

    def compose(self) -> ComposeResult:
        with Horizontal():
            for mode in ViewMode:
                yield Button(
                    VIEW_LABELS[mode],
                    id=f"tab-{mode.value}",
                    classes="active" if mode == self.current_view else "",
                )

    def watch_current_view(self, view: ViewMode) -> None:
        for btn in self.query(Button):
            if btn.id == f"tab-{view.value}":
                btn.add_class("active")
            else:
                btn.remove_class("active")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("tab-"):
            view_name = event.button.id.replace("tab-", "")
            self.current_view = ViewMode(view_name)
            self.app.post_message(ViewChanged(self.current_view))


class ViewChanged:
    def __init__(self, view: ViewMode) -> None:
        self.view = view


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


class TimelineApp(App[None]):
    CSS = """
    TimelineApp {
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

    def on_view_changed(self, event: ViewChanged) -> None:
        self.current_view = event.view
