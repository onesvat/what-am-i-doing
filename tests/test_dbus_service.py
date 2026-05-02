from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from waid.dbus_service import DaemonInterface, _disconnect_bus
from waid.models import (
    DisplayRow,
    PanelStateRecord,
    RefreshResult,
    UIStateRecord,
    utcnow,
)


async def _noop_reload() -> RefreshResult:
    return RefreshResult(success=True, message="ok")


async def _noop_set_tracking(enabled: bool) -> None:
    pass


async def _noop_pin_task(task_path: str) -> None:
    pass


class DBusServiceTest(unittest.IsolatedAsyncioTestCase):
    def test_refresh_taxonomy_alias_is_removed(self) -> None:
        self.assertFalse(hasattr(DaemonInterface, "RefreshTaxonomy"))

    def test_panel_properties_follow_internal_state(self) -> None:
        initial = PanelStateRecord.disconnected(
            revision=0,
            published_at=utcnow(),
            catalog_hash="hash-0",
        )
        initial_ui = UIStateRecord.from_panel_state(
            initial,
            tracking_enabled=True,
            display_label="disconnected",
            display_rows=[],
        )
        interface = DaemonInterface(
            _noop_reload,
            _noop_set_tracking,
            _noop_pin_task,
            initial,
            initial_ui,
            True,
        )

        self.assertEqual(0, interface.PanelRevision)
        self.assertEqual("disconnected", interface.PanelKind)
        self.assertEqual("", interface.PanelPath)
        self.assertEqual("", interface.PanelTaskPath)
        self.assertEqual("network-offline-symbolic", interface.PanelIconName)
        self.assertEqual("hash-0", interface.PanelCatalogHash)

        updated = PanelStateRecord.classified(
            revision=7,
            path="work/project-a",
            top_level_id="work",
            top_level_label="work",
            icon_name="laptop-symbolic",
            published_at=utcnow(),
            catalog_hash="abc123",
            task_path="project-a",
        )
        interface.update_panel_state(updated)

        self.assertEqual(7, interface.PanelRevision)
        self.assertEqual("classified", interface.PanelKind)
        self.assertEqual("work/project-a", interface.PanelPath)
        self.assertEqual("project-a", interface.PanelTaskPath)
        self.assertEqual("work", interface.PanelTopLevelId)
        self.assertEqual("work", interface.PanelTopLevelLabel)
        self.assertEqual("laptop-symbolic", interface.PanelIconName)
        self.assertEqual("abc123", interface.PanelCatalogHash)

    def test_get_ui_state_returns_current_payload(self) -> None:
        panel_state = PanelStateRecord.unclassified(
            revision=2,
            published_at=utcnow(),
            catalog_hash="hash-1",
        )
        ui_state = UIStateRecord.from_panel_state(
            panel_state,
            tracking_enabled=True,
            display_label="unknown",
            display_rows=[
                DisplayRow(
                    path="work/project-a",
                    label="work/project-a",
                    icon_name="laptop-symbolic",
                    seconds=120,
                )
            ],
        )
        interface = DaemonInterface(
            _noop_reload,
            _noop_set_tracking,
            _noop_pin_task,
            panel_state,
            ui_state,
            True,
        )

        payload = json.loads(interface._ui_state_json)

        self.assertEqual("unknown", payload["display_label"])
        self.assertEqual("hash-1", payload["catalog_hash"])
        self.assertEqual("work/project-a", payload["display_rows"][0]["path"])
        self.assertIsNone(payload["task_path"])

    def test_legacy_status_json_uses_catalog_hash(self) -> None:
        panel_state = PanelStateRecord.unclassified(
            revision=2,
            published_at=utcnow(),
            catalog_hash="hash-1",
        )
        ui_state = UIStateRecord.from_panel_state(
            panel_state,
            tracking_enabled=True,
            display_label="unknown",
            display_rows=[],
        )
        interface = DaemonInterface(
            _noop_reload,
            _noop_set_tracking,
            _noop_pin_task,
            panel_state,
            ui_state,
            True,
        )

        payload = json.loads(interface._legacy_status_json)
        self.assertEqual("unclassified", payload["current_path"])
        self.assertIsNone(payload["task_path"])
        self.assertEqual("unclassified", payload["top_level"])
        self.assertEqual("help-about-symbolic", payload["icon"])
        self.assertEqual("hash-1", payload["catalog_hash"])

    async def test_disconnect_bus_waits_for_actual_disconnect(self) -> None:
        bus = Mock()
        bus.wait_for_disconnect = AsyncMock()

        await _disconnect_bus(bus)

        bus.disconnect.assert_called_once_with()
        bus.wait_for_disconnect.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
