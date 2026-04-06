from __future__ import annotations

import asyncio

from dbus_next import BusType
from dbus_next.aio import MessageBus

from ..constants import TRACKER_BUS_NAME, TRACKER_INTERFACE, TRACKER_OBJECT_PATH
from ..models import ProviderSnapshot, ProviderState
from .base import Provider, ProviderCallback


DBUS_BUS_NAME = "org.freedesktop.DBus"
DBUS_OBJECT_PATH = "/org/freedesktop/DBus"
DBUS_INTERFACE = "org.freedesktop.DBus"


class GnomeProvider(Provider):
    async def snapshot(self) -> ProviderSnapshot:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        try:
            tracker = await self._tracker_interface(bus)
            return await self._snapshot_from_interface(tracker, default_revision=1)
        finally:
            bus.disconnect()

    async def monitor(self, callback: ProviderCallback) -> None:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        tracker = await self._tracker_interface(bus)
        dbus = await self._dbus_interface(bus)
        legacy = not hasattr(tracker, "call_get_snapshot")
        snapshot = await self._snapshot_from_interface(tracker, default_revision=1)
        current_revision = snapshot.revision
        await callback(snapshot)

        queue: asyncio.Queue[tuple[str, int | None, str | None]] = asyncio.Queue()

        if legacy:
            def on_state_changed(state_json: str) -> None:
                queue.put_nowait(("state", current_revision + 1, state_json))
        else:
            def on_state_changed(revision: int, state_json: str) -> None:
                queue.put_nowait(("state", int(revision), state_json))

        def on_name_owner_changed(name: str, old_owner: str, new_owner: str) -> None:
            if name != TRACKER_BUS_NAME:
                return
            if old_owner and old_owner != new_owner:
                queue.put_nowait(("tracker_lost", None, None))

        tracker.on_state_changed(on_state_changed)
        dbus.on_name_owner_changed(on_name_owner_changed)

        try:
            while True:
                kind, revision, payload = await queue.get()
                if kind == "tracker_lost":
                    raise RuntimeError("tracker extension disappeared from D-Bus")
                assert revision is not None
                if revision <= current_revision:
                    continue
                if not legacy and revision > current_revision + 1:
                    snapshot = await self._snapshot_from_interface(tracker, default_revision=current_revision + 1)
                    current_revision = snapshot.revision
                    await callback(snapshot)
                    continue
                assert payload is not None
                try:
                    state = ProviderState.model_validate_json(payload)
                except Exception:
                    snapshot = await self._snapshot_from_interface(tracker, default_revision=current_revision + 1)
                    current_revision = snapshot.revision
                    await callback(snapshot)
                    continue
                current_revision = revision
                await callback(ProviderSnapshot(revision=revision, state=state))
        finally:
            tracker.off_state_changed(on_state_changed)
            dbus.off_name_owner_changed(on_name_owner_changed)
            bus.disconnect()

    async def _tracker_interface(self, bus: MessageBus):
        introspection = await bus.introspect(TRACKER_BUS_NAME, TRACKER_OBJECT_PATH)
        obj = bus.get_proxy_object(TRACKER_BUS_NAME, TRACKER_OBJECT_PATH, introspection)
        return obj.get_interface(TRACKER_INTERFACE)

    async def _dbus_interface(self, bus: MessageBus):
        introspection = await bus.introspect(DBUS_BUS_NAME, DBUS_OBJECT_PATH)
        obj = bus.get_proxy_object(DBUS_BUS_NAME, DBUS_OBJECT_PATH, introspection)
        return obj.get_interface(DBUS_INTERFACE)

    async def _snapshot_from_interface(self, tracker, *, default_revision: int) -> ProviderSnapshot:
        if hasattr(tracker, "call_get_snapshot"):
            result = await tracker.call_get_snapshot()
            if not isinstance(result, list) or len(result) != 2:
                raise RuntimeError(f"unexpected GetSnapshot payload: {result!r}")
            revision, payload = result
        else:
            payload = await tracker.call_get_current_state()
            revision = default_revision
        return ProviderSnapshot(
            revision=int(revision),
            state=ProviderState.model_validate_json(payload),
        )
