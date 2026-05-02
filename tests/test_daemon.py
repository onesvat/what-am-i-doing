from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.constants import DEBOUNCE_SECONDS
from what_am_i_doing.daemon import describe_catalog_reload
from what_am_i_doing.models import (
    ProviderSnapshot,
    ProviderState,
    WindowInfo,
)


class DaemonTextTest(unittest.TestCase):
    def test_describe_catalog_reload_reports_unchanged_hash(self) -> None:
        message = describe_catalog_reload(
            {"work/project-a", "idle"},
            {"work/project-a", "idle"},
            "abcdef123456",
        )
        self.assertEqual("Loaded 2 catalog entries (unchanged, hash=abcdef12)", message)

    def test_describe_catalog_reload_reports_added_and_removed_paths(self) -> None:
        message = describe_catalog_reload(
            {"work/project-a", "browsing/reference"},
            {"work/project-a", "admin/inbox"},
            "1234567890abcdef",
        )
        self.assertIn("Loaded 2 catalog entries", message)
        self.assertIn("hash=12345678", message)
        self.assertIn("added: admin/inbox", message)
        self.assertIn("removed: browsing/reference", message)


class DaemonDebounceTest(unittest.TestCase):
    def test_rapid_snapshots_are_debounced(self) -> None:
        async def run_test() -> None:
            with patch("what_am_i_doing.daemon.GnomeProvider"):
                with patch("what_am_i_doing.daemon.DaemonDBusService"):
                    with patch("what_am_i_doing.daemon.load_config") as mock_load:
                        with patch("what_am_i_doing.daemon.load_tasks") as mock_tasks:
                            with patch("what_am_i_doing.daemon.ensure_state_dir"):
                                with patch(
                                    "what_am_i_doing.daemon.load_status"
                                ) as mock_status:
                                    from what_am_i_doing.daemon import ActivityDaemon
                                    from what_am_i_doing.config import AppConfig

                                    mock_load.return_value = MagicMock(
                                        spec=AppConfig,
                                        state_dir="/tmp/waid-test",
                                        idle_threshold_seconds=60,
                                        classify_idle=True,
                                    )
                                    mock_tasks.return_value = []
                                    mock_status.return_value = None

                                    daemon = ActivityDaemon.__new__(ActivityDaemon)
                                    daemon.config = mock_load.return_value
                                    daemon._debounce_task = None
                                    daemon._pending_snapshot = None
                                    daemon._debounce_lock = asyncio.Lock()
                                    daemon.runtime = MagicMock(tracking_enabled=True)

                                    process_mock = AsyncMock()
                                    daemon._process_snapshot = process_mock
                                    daemon._log_raw_event = MagicMock()

                                    def make_snapshot(rev: int, title: str) -> ProviderSnapshot:
                                        return ProviderSnapshot(
                                            revision=rev,
                                            state=ProviderState(
                                                focused_window=WindowInfo(
                                                    title=title, wm_class="test"
                                                ),
                                                timestamp=datetime.now(UTC),
                                            ),
                                        )

                                    await daemon.handle_snapshot(make_snapshot(1, "a"))
                                    await daemon.handle_snapshot(make_snapshot(2, "b"))
                                    await daemon.handle_snapshot(make_snapshot(3, "c"))

                                    process_mock.assert_not_called()

                                    await asyncio.sleep(DEBOUNCE_SECONDS + 0.1)

                                    process_mock.assert_called_once()
                                    call_snapshot = process_mock.call_args[0][0]
                                    self.assertEqual(3, call_snapshot.revision)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
