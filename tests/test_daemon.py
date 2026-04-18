from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.daemon import describe_catalog_reload


class DaemonTextTest(unittest.TestCase):
    def test_describe_catalog_reload_reports_unchanged_hash(self) -> None:
        message = describe_catalog_reload(
            {"work/project-a", "idle"},
            {"work/project-a", "idle"},
            "abcdef123456",
        )
        self.assertEqual("Loaded 2 catalog entries (unchanged, hash=abcdef12)", message)

    def test_describe_catalog_reload_reports_added_and_removed_paths(self) -> None:
        message = describe_catalog_reload(
            {"work/project-a", "browsing/reference"},
            {"work/project-a", "admin/inbox"},
            "1234567890abcdef",
        )
        self.assertIn("Loaded 2 catalog entries", message)
        self.assertIn("hash=12345678", message)
        self.assertIn("added: admin/inbox", message)
        self.assertIn("removed: browsing/reference", message)


if __name__ == "__main__":
    unittest.main()
