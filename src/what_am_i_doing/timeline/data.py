from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from ..models import SpanRecord


class Period(str, Enum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    ALL = "all"


def date_key(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def hour_key(dt: datetime) -> int:
    return dt.hour


def spans_by_hour(
    spans: list[SpanRecord], target_date: datetime
) -> dict[int, list[SpanRecord]]:
    day_start = date_key(target_date)
    day_end = day_start + timedelta(days=1)
    result: dict[int, list[SpanRecord]] = defaultdict(list)
    for span in spans:
        if span.started_at >= day_end or span.ended_at < day_start:
            continue
        effective_start = max(span.started_at, day_start)
        effective_end = min(span.ended_at, day_end)
        current = effective_start
        while current < effective_end:
            hour = hour_key(current)
            hour_end = current.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=1
            )
            chunk_end = min(effective_end, hour_end)
            chunk_span = SpanRecord(
                path=span.path,
                top_level=span.top_level,
                started_at=current,
                ended_at=chunk_end,
                duration_seconds=(chunk_end - current).total_seconds(),
            )
            result[hour].append(chunk_span)
            current = chunk_end
    return dict(sorted(result.items()))


def spans_by_day(
    spans: list[SpanRecord], week_start: datetime
) -> dict[datetime, list[SpanRecord]]:
    result: dict[datetime, list[SpanRecord]] = defaultdict(list)
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_key = date_key(day)
        for span in spans:
            span_day = date_key(span.started_at)
            if span_day == day_key:
                result[day_key].append(span)
    return dict(sorted(result.items()))


def contribution_data(spans: list[SpanRecord], year: int) -> dict[datetime, float]:
    year_start = datetime(year, 1, 1, tzinfo=UTC)
    year_end = datetime(year + 1, 1, 1, tzinfo=UTC)
    result: dict[datetime, float] = defaultdict(float)
    for span in spans:
        if span.started_at < year_start or span.started_at >= year_end:
            continue
        day_key = date_key(span.started_at)
        result[day_key] += span.duration_seconds
    return dict(sorted(result.items()))


def category_totals(spans: list[SpanRecord], period: Period) -> dict[str, float]:
    now = datetime.now(tz=UTC)
    day_start = date_key(now)
    window_start: datetime | None = {
        Period.TODAY: day_start,
        Period.WEEK: day_start - timedelta(days=day_start.weekday()),
        Period.MONTH: day_start.replace(day=1),
        Period.ALL: None,
    }[period]
    by_top: dict[str, float] = defaultdict(float)
    by_path: dict[str, float] = defaultdict(float)
    for span in spans:
        if window_start is not None and span.ended_at < window_start:
            continue
        by_top[span.top_level] += span.duration_seconds
        by_path[span.path] += span.duration_seconds
    return {"by_top": dict(by_top), "by_path": dict(by_path)}


def format_duration(seconds: float) -> str:
    total_minutes = round(seconds / 60)
    if total_minutes < 1:
        return "<1m"
    hours, minutes = divmod(total_minutes, 60)
    if hours == 0:
        return f"{minutes}m"
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes}m"


def format_hours(seconds: float) -> str:
    hours = seconds / 3600
    return f"{hours:.1f}h"


def daily_summary(spans: list[SpanRecord], target_date: datetime) -> dict[str, Any]:
    by_hour = spans_by_hour(spans, target_date)
    totals = defaultdict(float)
    for hour_spans in by_hour.values():
        for span in hour_spans:
            totals[span.path] += span.duration_seconds
    total_seconds = sum(totals.values())
    return {
        "date": date_key(target_date),
        "by_hour": by_hour,
        "by_path": dict(sorted(totals.items(), key=lambda x: x[1], reverse=True)),
        "total_seconds": total_seconds,
        "active_hours": len(by_hour),
    }


def weekly_summary(spans: list[SpanRecord], week_start: datetime) -> dict[str, Any]:
    by_day = spans_by_day(spans, week_start)
    totals = defaultdict(float)
    for day_spans in by_day.values():
        for span in day_spans:
            totals[span.top_level] += span.duration_seconds
    total_seconds = sum(totals.values())
    return {
        "week_start": week_start,
        "by_day": by_day,
        "by_top": dict(sorted(totals.items(), key=lambda x: x[1], reverse=True)),
        "total_seconds": total_seconds,
    }
