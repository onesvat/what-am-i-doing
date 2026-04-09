from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.__main__ import _run_init, build_parser


class MainCliTest(unittest.TestCase):
    def test_stats_parser_keeps_json_and_period(self) -> None:
        args = build_parser().parse_args(["stats", "--json", "--period", "week"])

        self.assertEqual("stats", args.command)
        self.assertTrue(args.json)
        self.assertEqual("week", args.period)

    def test_timeline_parser_keeps_view_and_theme(self) -> None:
        args = build_parser().parse_args(["timeline", "--view", "weekly", "--theme", "teal"])

        self.assertEqual("timeline", args.command)
        self.assertEqual("weekly", args.view)
        self.assertEqual("teal", args.theme)

    def test_refresh_parser_keeps_local_flag(self) -> None:
        args = build_parser().parse_args(["refresh", "--local"])

        self.assertEqual("refresh", args.command)
        self.assertTrue(args.local)

    def test_init_existing_config_exits_cleanly_without_tty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("version: 1\n", encoding="utf-8")

            with patch.object(sys.stdin, "isatty", return_value=False):
                with self.assertRaises(SystemExit) as ctx:
                    _run_init(str(config_path), force=False)

        self.assertIn("config already exists", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
