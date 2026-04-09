from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..data import category_totals, format_duration, Period
from ..theme import get_theme


class StatsTable(Static):
    DEFAULT_CSS = """
    StatsTable {
        height: auto;
        padding: 0 1;
    }
    """

    period: reactive[Period] = reactive(Period.TODAY)
    sort_by: reactive[str] = reactive("time")
    theme_name: reactive[str] = reactive("green")

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def watch_period(self, period: Period) -> None:
        self._refresh()

    def watch_sort_by(self, sort_by: str) -> None:
        self._refresh()

    def watch_theme_name(self, theme_name: str) -> None:
        self._refresh()

    def _refresh(self) -> None:
        theme = get_theme(self.theme_name)
        totals = category_totals(self._spans, self.period)
        by_top = totals["by_top"]
        by_path = totals["by_path"]
        total_seconds = sum(by_top.values())

        period_label = {
            Period.TODAY: "Today",
            Period.WEEK: "This Week",
            Period.MONTH: "This Month",
            Period.ALL: "All Time",
        }[self.period]

        items = list(by_top.items())
        if self.sort_by == "time":
            items.sort(key=lambda x: x[1], reverse=True)
        else:
            items.sort(key=lambda x: x[0])

        max_seconds = items[0][1] if items else 1
        bar_width = 20

        text = Text()
        text.append(f"{period_label}\n", style="bold")
        text.append("\n")

        for top, top_secs in items:
            dur = format_duration(top_secs)
            pct = (top_secs / total_seconds * 100) if total_seconds > 0 else 0
            filled = max(1, int(top_secs / max_seconds * bar_width))
            bar = "█" * filled + "░" * (bar_width - filled)

            text.append(f"  {top:<24}", style=f"bold {theme.accent}")
            text.append(f" {dur:>8}", style="bold")
            text.append(f" ({pct:.0f}%)\n", style="dim")
            text.append(f"  {bar}\n", style=f"{theme.levels[2]}")

            subs = [(p, s) for p, s in by_path.items() if p.startswith(top + "/")]
            subs.sort(key=lambda x: x[1], reverse=True)
            for path, secs in subs[:5]:
                sub_dur = format_duration(secs)
                sub_pct = (secs / total_seconds * 100) if total_seconds > 0 else 0
                text.append(f"    {path:<22}", style="dim")
                text.append(f" {sub_dur:>8}", style="")
                text.append(f" ({sub_pct:.0f}%)\n", style="dim")

        text.append(f"\n  {'─' * 38}\n", style="dim")
        text.append(f"  {'Total':<24}", style="bold")
        text.append(f" {format_duration(total_seconds):>8}\n", style="bold")

        self.update(text)

    def on_mount(self) -> None:
        self._refresh()


class StatsView(Widget):
    DEFAULT_CSS = """
    StatsView {
        height: 100%;
    }
    """

    period: reactive[Period] = reactive(Period.TODAY)
    theme_name: reactive[str] = reactive("green")

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def compose(self) -> ComposeResult:
        yield StatsTable(spans=self._spans)

    def watch_period(self, period: Period) -> None:
        table = self.query_one(StatsTable)
        table.period = period

    def watch_theme_name(self, theme_name: str) -> None:
        try:
            table = self.query_one(StatsTable)
            table.theme_name = theme_name
        except Exception:
            pass

    def on_mount(self) -> None:
        table = self.query_one(StatsTable)
        table.period = self.period
        table.theme_name = self.theme_name
