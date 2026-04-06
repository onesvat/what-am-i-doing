from __future__ import annotations

import sys
import unittest
from pathlib import Path
import json
import hashlib

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.models import (
    ProviderSnapshot,
    ProviderState,
    WindowInfo,
    Taxonomy,
    TaxonomyNode,
    utcnow,
)


class DaemonCacheTest(unittest.TestCase):
    def test_decision_key_excludes_revision(self):
        window = WindowInfo(
            title="test window",
            wm_class="kitty",
            workspace=1,
        )
        state1 = ProviderState(timestamp=utcnow(), focused_window=window)
        state2 = ProviderState(timestamp=utcnow(), focused_window=window)

        snapshot1 = ProviderSnapshot(revision=100, state=state1)
        snapshot2 = ProviderSnapshot(revision=200, state=state2)

        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="coding", description="Coding")]
        )
        taxonomy_hash = taxonomy.fingerprint()

        def make_key(snapshot, prev_sel, tax_hash):
            window = snapshot.state.focused_window
            normalized = {
                "title": window.title if window else "",
                "wm_class": window.wm_class if window else "",
                "wm_class_instance": window.wm_class_instance if window else None,
                "workspace_name": window.workspace_name if window else None,
                "active_workspace_name": snapshot.state.active_workspace_name,
                "fullscreen": window.fullscreen if window else False,
                "maximized": window.maximized if window else False,
                "screen_locked": snapshot.state.screen_locked,
                "idle_time_seconds": snapshot.state.idle_time_seconds,
                "previous_selection": prev_sel,
                "taxonomy_hash": tax_hash,
            }
            serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
            return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        key1 = make_key(snapshot1, None, taxonomy_hash)
        key2 = make_key(snapshot2, None, taxonomy_hash)

        self.assertEqual(
            key1,
            key2,
            "Cache keys should match for identical window state despite different revisions",
        )


if __name__ == "__main__":
    unittest.main()
