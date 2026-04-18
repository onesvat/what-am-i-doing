from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.providers.gnome import GnomeProvider


class GnomeProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_bus_waits_for_disconnect(self) -> None:
        provider = GnomeProvider()
        bus = Mock()
        bus.wait_for_disconnect = AsyncMock()

        await provider._disconnect_bus(bus)

        bus.disconnect.assert_called_once_with()
        bus.wait_for_disconnect.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
