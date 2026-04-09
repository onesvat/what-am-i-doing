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
                "open_windows": [
                    {
                        "title": open_window.title,
                        "wm_class": open_window.wm_class,
                        "wm_class_instance": open_window.wm_class_instance,
                        "app_id": open_window.app_id,
                        "workspace": open_window.workspace,
                        "workspace_name": open_window.workspace_name,
                        "z_order": open_window.z_order,
                    }
                    for open_window in sorted(
                        snapshot.state.open_windows,
                        key=lambda item: (
                            item.z_order is None,
                            item.z_order if item.z_order is not None else 9999,
                            item.wm_class,
                            item.title,
                        ),
                    )
                    if open_window.title or open_window.wm_class
                ],
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

    def test_decision_key_changes_when_open_windows_change(self):
        focused = WindowInfo(
            title="repo docs",
            wm_class="org.mozilla.firefox",
            workspace=1,
        )
        state1 = ProviderState(
            timestamp=utcnow(),
            focused_window=focused,
            open_windows=[
                focused,
                WindowInfo(title="app.py", wm_class="code", workspace=1),
            ],
        )
        state2 = ProviderState(
            timestamp=utcnow(),
            focused_window=focused,
            open_windows=[
                focused,
                WindowInfo(title="calendar", wm_class="org.gnome.Calendar", workspace=1),
            ],
        )
        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="coding", description="Coding")]
        )
        taxonomy_hash = taxonomy.fingerprint()

        def make_key(state):
            window = state.focused_window
            normalized = {
                "title": window.title if window else "",
                "wm_class": window.wm_class if window else "",
                "wm_class_instance": window.wm_class_instance if window else None,
                "workspace_name": window.workspace_name if window else None,
                "active_workspace_name": state.active_workspace_name,
                "fullscreen": window.fullscreen if window else False,
                "maximized": window.maximized if window else False,
                "open_windows": [
                    {
                        "title": open_window.title,
                        "wm_class": open_window.wm_class,
                        "wm_class_instance": open_window.wm_class_instance,
                        "app_id": open_window.app_id,
                        "workspace": open_window.workspace,
                        "workspace_name": open_window.workspace_name,
                        "z_order": open_window.z_order,
                    }
                    for open_window in sorted(
                        state.open_windows,
                        key=lambda item: (
                            item.z_order is None,
                            item.z_order if item.z_order is not None else 9999,
                            item.wm_class,
                            item.title,
                        ),
                    )
                    if open_window.title or open_window.wm_class
                ],
                "screen_locked": state.screen_locked,
                "idle_time_seconds": state.idle_time_seconds,
                "previous_selection": None,
                "taxonomy_hash": taxonomy_hash,
            }
            serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
            return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        self.assertNotEqual(make_key(state1), make_key(state2))


if __name__ == "__main__":
    unittest.main()
