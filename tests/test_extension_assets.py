from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.constants import EXTENSION_UUID


class ExtensionAssetsTest(unittest.TestCase):
    def test_packaged_extension_assets_match_canonical_files(self) -> None:
        canonical_dir = ROOT / "extensions" / "gnome"
        packaged_dir = ROOT / "src" / "what_am_i_doing" / "resources" / "gnome"

        for relative_path in ("metadata.json", "extension.js"):
            with self.subTest(relative_path=relative_path):
                canonical = (canonical_dir / relative_path).read_text(encoding="utf-8")
                packaged = (packaged_dir / relative_path).read_text(encoding="utf-8")
                self.assertEqual(canonical, packaged)

    def test_metadata_targets_supported_gnome_release(self) -> None:
        metadata_path = ROOT / "extensions" / "gnome" / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(EXTENSION_UUID, metadata["uuid"])
        self.assertEqual(["49"], metadata["shell-version"])
        self.assertTrue(metadata["url"].startswith("https://"))

    def test_extension_stats_hide_sub_minute_rows(self) -> None:
        extension_path = ROOT / "extensions" / "gnome" / "extension.js"
        source = extension_path.read_text(encoding="utf-8")

        self.assertIn("_shouldShowStatRow(seconds)", source)
        self.assertIn("return seconds >= 60;", source)
        self.assertIn("if (this._shouldShowStatRow(catSeconds))", source)
        self.assertIn("if (this._shouldShowStatRow(childSeconds))", source)


if __name__ == "__main__":
    unittest.main()
