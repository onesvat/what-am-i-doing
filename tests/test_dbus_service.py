from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.dbus_service import DaemonInterface
from what_am_i_doing.models import PanelStateRecord, utcnow


async def _noop_refresh() -> None:
    return None


class DBusServiceTest(unittest.TestCase):
    def test_panel_properties_follow_internal_state(self) -> None:
        initial = PanelStateRecord.disconnected(revision=0, published_at=utcnow())
        interface = DaemonInterface(_noop_refresh, initial)

        self.assertEqual(0, interface.PanelRevision)
        self.assertEqual("disconnected", interface.PanelKind)
        self.assertEqual("", interface.PanelPath)
        self.assertEqual("network-offline-symbolic", interface.PanelIconName)
        self.assertEqual("", interface.PanelTaxonomyHash)

        updated = PanelStateRecord.classified(
            revision=7,
            path="coding/project-x",
            top_level_id="coding",
            top_level_label="coding",
            icon_name="laptop-symbolic",
            published_at=utcnow(),
            taxonomy_hash="abc123",
        )
        interface.update_panel_state(updated)

        self.assertEqual(7, interface.PanelRevision)
        self.assertEqual("classified", interface.PanelKind)
        self.assertEqual("coding/project-x", interface.PanelPath)
        self.assertEqual("coding", interface.PanelTopLevelId)
        self.assertEqual("coding", interface.PanelTopLevelLabel)
        self.assertEqual("laptop-symbolic", interface.PanelIconName)
        self.assertEqual("abc123", interface.PanelTaxonomyHash)
        self.assertEqual(7, interface._panel_state.revision)
        self.assertEqual(updated.payload_json(), interface._panel_state_json)

    def test_legacy_status_json_stays_compatible(self) -> None:
        panel_state = PanelStateRecord.unclassified(
            revision=2,
            published_at=utcnow(),
            taxonomy_hash="hash-1",
        )
        interface = DaemonInterface(_noop_refresh, panel_state)

        payload = json.loads(interface._legacy_status_json)
        self.assertEqual("unclassified", payload["current_path"])
        self.assertEqual("unclassified", payload["top_level"])
        self.assertEqual("help-about-symbolic", payload["icon"])
        self.assertEqual("hash-1", payload["taxonomy_hash"])


if __name__ == "__main__":
    unittest.main()
