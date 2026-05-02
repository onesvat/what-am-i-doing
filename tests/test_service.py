from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from waid.service import render_unit


class ServiceTest(unittest.TestCase):
    def test_render_unit_contains_module_run_command(self) -> None:
        unit = render_unit()
        self.assertIn("-m waid --config", unit)
        self.assertIn("--config", unit)
        self.assertIn(" run", unit)
        self.assertIn("waid desktop activity tracker", unit)


if __name__ == "__main__":
    unittest.main()
