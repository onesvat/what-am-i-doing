from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..data import category_totals, format_duration, Period


class StatsTable(Static):
    DEFAULT_CSS = """
    StatsTable {
        height: auto;
        padding: 1;
    }
    """

    period: reactive[Period] = reactive(Period.TODAY)
    sort_by: reactive[str] = reactive("time")

    def __init__(self, spans: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spans = spans

    def watch_period(self, period: Period) -> None:
        self._refresh()

    def watch_sort_by(self, sort_by: str) -> None:
        self._refresh()

    def _refresh(self) -> None:
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

        lines: list[str] = []
        lines.append(f"\n{period_label}")
        lines.append("")

        items = list(by_top.items())
        if self.sort_by == "time":
            items.sort(key=lambda x: x[1], reverse=True)
        else:
            items.sort(key=lambda x: x[0])

        for top, top_secs in items:
            dur = format_duration(top_secs)
            pct = (top_secs / total_seconds * 100) if total_seconds > 0 else 0
            lines.append(f"  {top:<30} {dur:>8} ({pct:.0f}%)")
            subs = [(p, s) for p, s in by_path.items() if p.startswith(top + "/")]
            subs.sort(key=lambda x: x[1], reverse=True)
            for path, secs in subs[:5]:
                dur = format_duration(secs)
                lines.append(f"    {path:<28} {dur:>8}")

        lines.append("")
        lines.append(f"  {'─' * 42}")
        lines.append(f"  {'Total':<30} {format_duration(total_seconds):>8}")

        self.update("\n".join(lines))

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
        yield Static(
            "\nPress t (today), w (week), m (month), y (all) to change period\nPress s to toggle sort\n"
        )
        yield StatsTable(spans=self._spans)

    def watch_period(self, period: Period) -> None:
        table = self.query_one(StatsTable)
        table.period = period

    def on_mount(self) -> None:
        self.query_one(StatsTable).period = self.period
