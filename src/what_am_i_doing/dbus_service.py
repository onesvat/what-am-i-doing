from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

from dbus_next import BusType
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method, signal

from .constants import DAEMON_BUS_NAME, DAEMON_INTERFACE, DAEMON_OBJECT_PATH
from .models import PanelStateRecord, RefreshResult, UIStateRecord

log = logging.getLogger("waid.comm")

PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"


class DaemonInterface(ServiceInterface):
    def __init__(
        self,
        reload_callback: Callable[[], Awaitable[RefreshResult]],
        set_tracking_callback: Callable[[bool], Awaitable[None]],
        initial_panel_state: PanelStateRecord,
        initial_ui_state: UIStateRecord,
        initial_tracking_enabled: bool,
    ) -> None:
        super().__init__(DAEMON_INTERFACE)
        self._reload_callback = reload_callback
        self._set_tracking_callback = set_tracking_callback
        self._panel_state = initial_panel_state
        self._panel_state_json = initial_panel_state.payload_json()
        self._legacy_status_json = self._build_legacy_status_json(initial_panel_state)
        self._ui_state_json = initial_ui_state.model_dump_json()
        self._tracking_enabled = initial_tracking_enabled
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
    def PanelChoicesHash(self) -> "s":
        return self._panel_choices_hash

    @dbus_property(access=PropertyAccess.READ)
    def TrackingEnabled(self) -> "b":
        return self._tracking_enabled

    @method()
    def GetPanelState(self) -> "us":
        return [self._panel_state.revision, self._panel_state_json]

    @method()
    def GetUiState(self) -> "s":
        return self._ui_state_json

    @method()
    def GetStatus(self) -> "s":
        return self._legacy_status_json

    @method()
    async def ReloadConfig(self) -> "bs":
        result = await self._reload_callback()
        return [result.success, result.message]

    @method()
    async def SetTracking(self, enabled: "b") -> "":
        await self._set_tracking_callback(enabled)

    @signal()
    def PanelStateChanged(self, revision: "u", payload: "s") -> "us":
        return [revision, payload]

    @signal()
    def StatusChanged(self, payload: "s") -> "s":
        return payload

    @signal()
    def TrackingStateChanged(self, enabled: "b") -> "b":
        return enabled

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
                "PanelChoicesHash": self._panel_choices_hash,
            }
        )
        self.PanelStateChanged(panel_state.revision, self._panel_state_json)
        self.StatusChanged(self._legacy_status_json)

    def update_ui_state(self, ui_state: UIStateRecord) -> None:
        self._ui_state_json = ui_state.model_dump_json()

    def update_tracking_state(self, enabled: bool) -> None:
        self._tracking_enabled = enabled
        self.emit_properties_changed({"TrackingEnabled": self._tracking_enabled})
        self.TrackingStateChanged(enabled)

    def _set_panel_fields(self, panel_state: PanelStateRecord) -> None:
        self._panel_revision = panel_state.revision
        self._panel_kind = panel_state.kind
        self._panel_path = panel_state.path or ""
        self._panel_top_level_id = panel_state.top_level_id or ""
        self._panel_top_level_label = panel_state.top_level_label or ""
        self._panel_icon_name = panel_state.icon_name
        self._panel_published_at = panel_state.published_at.isoformat()
        self._panel_choices_hash = panel_state.choices_hash or ""

    def _build_legacy_status_json(self, panel_state: PanelStateRecord) -> str:
        payload = {
            "current_path": panel_state.path or panel_state.kind,
            "top_level": panel_state.top_level_label or panel_state.kind,
            "icon": panel_state.icon_name,
            "updated_at": panel_state.published_at.isoformat(),
            "choices_hash": panel_state.choices_hash,
        }
        return json.dumps(payload, sort_keys=True)


class DaemonDBusService:
    def __init__(
        self,
        reload_callback: Callable[[], Awaitable[RefreshResult]],
        set_tracking_callback: Callable[[bool], Awaitable[None]],
        initial_panel_state: PanelStateRecord,
        initial_ui_state: UIStateRecord,
        initial_tracking_enabled: bool,
    ) -> None:
        self._reload_callback = reload_callback
        self._set_tracking_callback = set_tracking_callback
        self._bus: MessageBus | None = None
        self.interface = DaemonInterface(
            reload_callback,
            set_tracking_callback,
            initial_panel_state,
            initial_ui_state,
            initial_tracking_enabled,
        )

    async def start(self) -> None:
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self._bus.export(DAEMON_OBJECT_PATH, self.interface)
        await self._bus.request_name(DAEMON_BUS_NAME)

    def update_panel_state(self, panel_state: PanelStateRecord) -> None:
        self.interface.update_panel_state(panel_state)

    def update_ui_state(self, ui_state: UIStateRecord) -> None:
        self.interface.update_ui_state(ui_state)

    def update_tracking_state(self, enabled: bool) -> None:
        self.interface.update_tracking_state(enabled)


async def _disconnect_bus(bus: MessageBus | None) -> None:
    if bus is None:
        return
    bus.disconnect()
    try:
        await bus.wait_for_disconnect()
    except Exception:
        pass


async def daemon_ui_state_payload() -> dict[str, object]:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        introspection = await bus.introspect(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH)
        obj = bus.get_proxy_object(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH, introspection)
        interface = obj.get_interface(DAEMON_INTERFACE)
        payload_json = await interface.call_get_ui_state()
        return json.loads(payload_json)
    finally:
        await _disconnect_bus(bus)


async def daemon_status_payload() -> dict[str, object]:
    return await daemon_ui_state_payload()


async def daemon_reload_config() -> tuple[bool, str]:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        introspection = await bus.introspect(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH)
        obj = bus.get_proxy_object(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH, introspection)
        interface = obj.get_interface(DAEMON_INTERFACE)
        return await interface.call_reload_config()
    finally:
        await _disconnect_bus(bus)


async def daemon_get_tracking() -> bool:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        introspection = await bus.introspect(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH)
        obj = bus.get_proxy_object(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH, introspection)
        properties = obj.get_interface(PROPERTIES_INTERFACE)
        value = await properties.call_get(DAEMON_INTERFACE, "TrackingEnabled")
        return bool(value.value)
    finally:
        await _disconnect_bus(bus)


async def daemon_set_tracking(enabled: bool) -> None:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        introspection = await bus.introspect(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH)
        obj = bus.get_proxy_object(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH, introspection)
        interface = obj.get_interface(DAEMON_INTERFACE)
        await interface.call_set_tracking(enabled)
    finally:
        await _disconnect_bus(bus)
