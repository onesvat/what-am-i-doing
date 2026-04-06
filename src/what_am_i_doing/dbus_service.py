from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

from dbus_next import BusType
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method, signal

from .constants import DAEMON_BUS_NAME, DAEMON_INTERFACE, DAEMON_OBJECT_PATH
from .models import PanelStateRecord

log = logging.getLogger("waid.comm")

PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"


class DaemonInterface(ServiceInterface):
    def __init__(
        self,
        refresh_callback: Callable[[], Awaitable[None]],
        initial_panel_state: PanelStateRecord,
    ) -> None:
        super().__init__(DAEMON_INTERFACE)
        self._refresh_callback = refresh_callback
        self._panel_state = initial_panel_state
        self._panel_state_json = initial_panel_state.payload_json()
        self._legacy_status_json = self._build_legacy_status_json(initial_panel_state)
        self._set_panel_fields(initial_panel_state)

    @dbus_property(access=PropertyAccess.READ)
    def PanelRevision(self) -> "u":
        return self._panel_revision

    @dbus_property(access=PropertyAccess.READ)
    def PanelKind(self) -> "s":
        return self._panel_kind

    @dbus_property(access=PropertyAccess.READ)
    def PanelPath(self) -> "s":
        return self._panel_path

    @dbus_property(access=PropertyAccess.READ)
    def PanelTopLevelId(self) -> "s":
        return self._panel_top_level_id

    @dbus_property(access=PropertyAccess.READ)
    def PanelTopLevelLabel(self) -> "s":
        return self._panel_top_level_label

    @dbus_property(access=PropertyAccess.READ)
    def PanelIconName(self) -> "s":
        return self._panel_icon_name

    @dbus_property(access=PropertyAccess.READ)
    def PanelPublishedAt(self) -> "s":
        return self._panel_published_at

    @dbus_property(access=PropertyAccess.READ)
    def PanelTaxonomyHash(self) -> "s":
        return self._panel_taxonomy_hash

    @method()
    def GetPanelState(self) -> "us":
        return [self._panel_state.revision, self._panel_state_json]

    @method()
    def GetStatus(self) -> "s":
        return self._legacy_status_json

    @method()
    async def RefreshTaxonomy(self) -> "b":
        await self._refresh_callback()
        return True

    @signal()
    def PanelStateChanged(self, revision: "u", payload: "s") -> "us":
        return [revision, payload]

    @signal()
    def StatusChanged(self, payload: "s") -> "s":
        return payload

    def update_panel_state(self, panel_state: PanelStateRecord) -> None:
        self._panel_state = panel_state
        self._panel_state_json = panel_state.payload_json()
        self._legacy_status_json = self._build_legacy_status_json(panel_state)
        self._set_panel_fields(panel_state)
        log.info(
            "send ext <- rev=%d kind=%s path=%s",
            panel_state.revision,
            panel_state.kind,
            panel_state.path or "-",
        )
        self.emit_properties_changed(
            {
                "PanelRevision": self._panel_revision,
                "PanelKind": self._panel_kind,
                "PanelPath": self._panel_path,
                "PanelTopLevelId": self._panel_top_level_id,
                "PanelTopLevelLabel": self._panel_top_level_label,
                "PanelIconName": self._panel_icon_name,
                "PanelPublishedAt": self._panel_published_at,
                "PanelTaxonomyHash": self._panel_taxonomy_hash,
            }
        )
        self.PanelStateChanged(panel_state.revision, self._panel_state_json)
        self.StatusChanged(self._legacy_status_json)

    def _set_panel_fields(self, panel_state: PanelStateRecord) -> None:
        self._panel_revision = panel_state.revision
        self._panel_kind = panel_state.kind
        self._panel_path = panel_state.path or ""
        self._panel_top_level_id = panel_state.top_level_id or ""
        self._panel_top_level_label = panel_state.top_level_label or ""
        self._panel_icon_name = panel_state.icon_name
        self._panel_published_at = panel_state.published_at.isoformat()
        self._panel_taxonomy_hash = panel_state.taxonomy_hash or ""

    def _build_legacy_status_json(self, panel_state: PanelStateRecord) -> str:
        payload = {
            "current_path": panel_state.path or panel_state.kind,
            "top_level": panel_state.top_level_label or panel_state.kind,
            "icon": panel_state.icon_name,
            "updated_at": panel_state.published_at.isoformat(),
            "taxonomy_hash": panel_state.taxonomy_hash,
        }
        return json.dumps(payload, sort_keys=True)


class DaemonDBusService:
    def __init__(
        self,
        refresh_callback: Callable[[], Awaitable[None]],
        initial_panel_state: PanelStateRecord,
    ) -> None:
        self._refresh_callback = refresh_callback
        self._bus: MessageBus | None = None
        self.interface = DaemonInterface(refresh_callback, initial_panel_state)

    async def start(self) -> None:
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self._bus.export(DAEMON_OBJECT_PATH, self.interface)
        await self._bus.request_name(DAEMON_BUS_NAME)

    def update_panel_state(self, panel_state: PanelStateRecord) -> None:
        self.interface.update_panel_state(panel_state)


async def daemon_status_payload() -> dict[str, object]:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        introspection = await bus.introspect(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH)
        obj = bus.get_proxy_object(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH, introspection)
        properties = obj.get_interface(PROPERTIES_INTERFACE)
        values = await properties.call_get_all(DAEMON_INTERFACE)
        if "PanelKind" in values:
            return {
                "schema_version": 1,
                "revision": values["PanelRevision"].value,
                "kind": values["PanelKind"].value,
                "path": values["PanelPath"].value or None,
                "top_level_id": values["PanelTopLevelId"].value or None,
                "top_level_label": values["PanelTopLevelLabel"].value or None,
                "icon_name": values["PanelIconName"].value,
                "published_at": values["PanelPublishedAt"].value,
                "taxonomy_hash": values["PanelTaxonomyHash"].value or None,
            }
        interface = obj.get_interface(DAEMON_INTERFACE)
        revision, payload_json = await interface.call_get_panel_state()
        payload = json.loads(payload_json)
        payload["revision"] = revision
        return payload
    finally:
        bus.disconnect()


async def daemon_refresh_taxonomy() -> bool:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        introspection = await bus.introspect(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH)
        obj = bus.get_proxy_object(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH, introspection)
        interface = obj.get_interface(DAEMON_INTERFACE)
        return await interface.call_refresh_taxonomy()
    finally:
        bus.disconnect()
