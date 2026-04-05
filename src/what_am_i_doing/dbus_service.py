from __future__ import annotations

import json
from typing import Awaitable, Callable

from dbus_next import BusType
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from .constants import DAEMON_BUS_NAME, DAEMON_INTERFACE, DAEMON_OBJECT_PATH
from .models import StatusRecord


class DaemonInterface(ServiceInterface):
    def __init__(self, refresh_callback: Callable[[], Awaitable[None]]) -> None:
        super().__init__(DAEMON_INTERFACE)
        self._refresh_callback = refresh_callback
        self._status_json = json.dumps(
            {"current_path": "unknown", "top_level": "unknown", "icon": "help-about-symbolic"}
        )

    @method()
    def GetStatus(self) -> "s":
        return self._status_json

    @method()
    async def RefreshTaxonomy(self) -> "b":
        await self._refresh_callback()
        return True

    @signal()
    def StatusChanged(self, payload: "s") -> "s":
        return payload

    def update_status(self, status: StatusRecord) -> None:
        self._status_json = status.model_dump_json()
        self.StatusChanged(self._status_json)


class DaemonDBusService:
    def __init__(self, refresh_callback: Callable[[], Awaitable[None]]) -> None:
        self._refresh_callback = refresh_callback
        self._bus: MessageBus | None = None
        self.interface = DaemonInterface(refresh_callback)

    async def start(self) -> None:
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self._bus.export(DAEMON_OBJECT_PATH, self.interface)
        await self._bus.request_name(DAEMON_BUS_NAME)

    def update_status(self, status: StatusRecord) -> None:
        self.interface.update_status(status)


async def daemon_status_json() -> str:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    introspection = await bus.introspect(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH)
    obj = bus.get_proxy_object(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH, introspection)
    interface = obj.get_interface(DAEMON_INTERFACE)
    return await interface.call_get_status()


async def daemon_refresh_taxonomy() -> bool:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    introspection = await bus.introspect(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH)
    obj = bus.get_proxy_object(DAEMON_BUS_NAME, DAEMON_OBJECT_PATH, introspection)
    interface = obj.get_interface(DAEMON_INTERFACE)
    return await interface.call_refresh_taxonomy()
