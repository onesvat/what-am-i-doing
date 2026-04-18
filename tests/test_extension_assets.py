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

    def test_extension_renders_rows_from_status_payload(self) -> None:
        extension_path = ROOT / "extensions" / "gnome" / "extension.js"
        source = extension_path.read_text(encoding="utf-8")

        self.assertIn("display_rows", source)
        self.assertIn("this._addDisplayRow(row)", source)
        self.assertIn("Reload Choices", source)
        self.assertIn("ReloadConfig", source)

    def test_extension_no_longer_reads_taxonomy_or_spans_files(self) -> None:
        extension_path = ROOT / "extensions" / "gnome" / "extension.js"
        source = extension_path.read_text(encoding="utf-8")

        self.assertNotIn("TAXONOMY_FILE", source)
        self.assertNotIn("SPANS_FILE", source)
        self.assertNotIn("RefreshTaxonomy", source)
        self.assertNotIn("_aggregateSpans", source)
        self.assertNotIn("_loadTaxonomy", source)


if __name__ == "__main__":
    unittest.main()
