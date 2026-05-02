from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from waid.__main__ import _run_init, _timeline_payload, _window_start_for_period, build_parser
from waid.models import AppPaths


class MainCliTest(unittest.TestCase):
    def test_stats_parser_keeps_json_and_period(self) -> None:
        args = build_parser().parse_args(["stats", "--json", "--period", "week"])

        self.assertEqual("stats", args.command)
        self.assertTrue(args.json)
        self.assertEqual("week", args.period)

    def test_refresh_parser_keeps_local_flag(self) -> None:
        args = build_parser().parse_args(["refresh", "--local"])

        self.assertEqual("refresh", args.command)
        self.assertTrue(args.local)

    def test_timeline_parser_keeps_json_and_period(self) -> None:
        args = build_parser().parse_args(["timeline", "--json", "--period", "week"])

        self.assertEqual("timeline", args.command)
        self.assertTrue(args.json)
        self.assertEqual("week", args.period)

    def test_init_existing_config_exits_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("version: 2\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as ctx:
                _run_init(str(config_path), force=False)

        self.assertIn("config already exists", str(ctx.exception))

    def test_timeline_payload_segments_rows_and_includes_non_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            paths = AppPaths.from_state_dir(state_dir)
            now = datetime.now(tz=UTC)
            t1 = now - timedelta(minutes=20)
            t2 = now - timedelta(minutes=10)
            t3 = now - timedelta(minutes=5)
            lines = [
                {"ts": t1.isoformat(), "event": "activity_change", "kind": "classified", "activity_path": "coding/terminal", "task_path": "fix-bug", "wm_class": "kitty", "title": "repo"},
                {"ts": t2.isoformat(), "event": "activity_change", "kind": "paused", "activity_path": None, "task_path": None, "wm_class": "", "title": ""},
                {"ts": t3.isoformat(), "event": "activity_change", "kind": "disconnected", "activity_path": None, "task_path": None, "wm_class": "gnome-shell", "title": "Shell"},
            ]
            with paths.activity_log.open("w", encoding="utf-8") as handle:
                handle.write("not json\n")
                handle.write(json.dumps({"event": "window_change"}) + "\n")
                for entry in lines:
                    handle.write(json.dumps(entry) + "\n")

            with patch("waid.__main__.AppPaths.default", return_value=paths):
                payload = _timeline_payload("all")

        rows = payload["rows"]
        self.assertEqual(3, len(rows))
        self.assertEqual(lines[0]["activity_path"], rows[0]["activity_or_kind"])
        self.assertEqual(lines[0]["task_path"], rows[0]["task_or_dash"])
        self.assertEqual(lines[1]["kind"], rows[1]["activity_or_kind"])
        self.assertEqual("-", rows[1]["task_or_dash"])
        self.assertEqual(lines[2]["kind"], rows[2]["activity_or_kind"])
        self.assertEqual(t2.replace(microsecond=0), datetime.fromisoformat(rows[0]["end"]).replace(microsecond=0))
        self.assertEqual(t3.replace(microsecond=0), datetime.fromisoformat(rows[1]["end"]).replace(microsecond=0))
        last_end = datetime.fromisoformat(rows[2]["end"])
        self.assertLessEqual(abs((datetime.now(tz=UTC) - last_end).total_seconds()), 5.0)

    def test_timeline_payload_period_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            paths = AppPaths.from_state_dir(state_dir)
            now = datetime.now(tz=UTC)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = _window_start_for_period("week", now)
            month_start = _window_start_for_period("month", now)
            assert week_start is not None
            assert month_start is not None
            old_ts = min(week_start, month_start) - timedelta(days=1)
            events = [
                {"ts": (day_start + timedelta(hours=1)).isoformat(), "event": "activity_change", "kind": "classified", "activity_path": "coding/ide", "task_path": None, "wm_class": "code", "title": "today"},
                {"ts": (week_start + timedelta(hours=1)).isoformat(), "event": "activity_change", "kind": "classified", "activity_path": "communication/chat", "task_path": None, "wm_class": "slack", "title": "week"},
                {"ts": (month_start + timedelta(hours=1)).isoformat(), "event": "activity_change", "kind": "classified", "activity_path": "admin", "task_path": None, "wm_class": "firefox", "title": "month"},
                {"ts": old_ts.isoformat(), "event": "activity_change", "kind": "unknown", "activity_path": None, "task_path": None, "wm_class": "", "title": "old"},
            ]
            with paths.activity_log.open("w", encoding="utf-8") as handle:
                for entry in events:
                    handle.write(json.dumps(entry) + "\n")

            with patch("waid.__main__.AppPaths.default", return_value=paths):
                today_rows = _timeline_payload("today")["rows"]
                week_rows = _timeline_payload("week")["rows"]
                month_rows = _timeline_payload("month")["rows"]
                all_rows = _timeline_payload("all")["rows"]

        starts = [datetime.fromisoformat(item["ts"]) for item in events]
        today_start = _window_start_for_period("today", now)
        week_start = _window_start_for_period("week", now)
        month_start = _window_start_for_period("month", now)
        self.assertEqual(sum(1 for ts in starts if today_start is not None and ts >= today_start), len(today_rows))
        self.assertEqual(sum(1 for ts in starts if week_start is not None and ts >= week_start), len(week_rows))
        self.assertEqual(sum(1 for ts in starts if month_start is not None and ts >= month_start), len(month_rows))
        self.assertEqual(4, len(all_rows))


if __name__ == "__main__":
    unittest.main()
