from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ExtensionAssetsTest(unittest.TestCase):
    def test_extension_strings_match_catalog_terms(self) -> None:
        source = (ROOT / "src/what_am_i_doing/resources/gnome/extension.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("Reload Catalog", source)
        self.assertIn("No activities or tasks configured", source)
        self.assertIn("task_path", source)


if __name__ == "__main__":
    unittest.main()
