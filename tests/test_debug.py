from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.debug import DebugLogger, debug_enabled


class DebugTest(unittest.TestCase):
    def test_debug_enabled_reads_env_var(self) -> None:
        old = os.environ.get("WAID_DEBUG")
        try:
            os.environ["WAID_DEBUG"] = "1"
            self.assertTrue(debug_enabled())
            os.environ["WAID_DEBUG"] = "false"
            self.assertFalse(debug_enabled())
        finally:
            if old is None:
                os.environ.pop("WAID_DEBUG", None)
            else:
                os.environ["WAID_DEBUG"] = old

    def test_debug_logger_writes_jsonl_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "debug.jsonl"
            logger = DebugLogger(path, enabled=True)
            logger.log("classifier_result", result="unknown")
            text = path.read_text(encoding="utf-8")
            self.assertIn('"event": "classifier_result"', text)
            self.assertIn('"result": "unknown"', text)


if __name__ == "__main__":
    unittest.main()
