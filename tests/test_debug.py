from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.debug import DebugLogger, debug_enabled, format_debug_entry, load_debug_entries


class DebugTest(unittest.TestCase):
    def test_debug_enabled_reads_env_var(self) -> None:
        old = os.environ.get("WAID_DEBUG")
        try:
            os.environ["WAID_DEBUG"] = "1"
            self.assertTrue(debug_enabled())
            os.environ["WAID_DEBUG"] = "false"
            self.assertFalse(debug_enabled())
        finally:
            if old is None:
                os.environ.pop("WAID_DEBUG", None)
            else:
                os.environ["WAID_DEBUG"] = old

    def test_debug_logger_writes_jsonl_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "debug.jsonl"
            logger = DebugLogger(path, enabled=True)
            logger.log("classifier_result", result="unknown")
            text = path.read_text(encoding="utf-8")
            self.assertIn('"event": "classifier_result"', text)
            self.assertIn('"result": "unknown"', text)

    def test_format_debug_entry_is_human_readable(self) -> None:
        rendered = format_debug_entry(
            {
                "ts": "2026-04-06T07:30:00+00:00",
                "event": "activity_changed",
                "previous_path": "unknown",
                "selected_path": "coding/fix_bug",
            }
        )
        self.assertIn("activity:", rendered)
        self.assertIn("unknown -> coding/fix_bug", rendered)

    def test_load_debug_entries_reads_recent_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "debug.jsonl"
            path.write_text(
                '{"event":"one","ts":"2026-04-06T07:30:00+00:00"}\n'
                '{"event":"two","ts":"2026-04-06T07:31:00+00:00"}\n',
                encoding="utf-8",
            )
            entries = load_debug_entries(path, lines=1)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["event"], "two")

    def test_debug_logs_command_renders_plain_text(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            env = os.environ.copy()
            env["HOME"] = home_dir
            debug_dir = Path(home_dir) / ".local" / "state" / "waid"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / "debug.jsonl").write_text(
                '{"event":"classifier_result","attempt":0,"result":"coding","ts":"2026-04-06T07:30:00+00:00"}\n',
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, "-m", "what_am_i_doing", "debug", "logs", "--lines", "1"],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("classifier: attempt 0 returned coding", proc.stdout)


if __name__ == "__main__":
    unittest.main()
