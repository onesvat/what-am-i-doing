from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.config import AppConfig, interpolate_text, load_config


class ConfigTest(unittest.TestCase):
    def test_load_config_adds_unknown_category(self) -> None:
        yaml_text = textwrap.dedent(
            """
            version: 1
            model:
              base_url: http://localhost:11434/v1
              name: gemma
            generator:
              categories:
                - name: coding
              instructions: |
                Today's tasks:
                ${sp_today_tasks}
            classifier:
              instructions: |
                Mode: ${work_mode}
              params:
                work_mode: focused
            tools:
              context:
                sp_today_tasks:
                  run: ["sp", "list", "today"]
              actions:
                ha:
                  run: ["ha"]
            """
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml") as handle:
            handle.write(yaml_text)
            handle.flush()
            config = load_config(handle.name)
        self.assertIn("unknown", {node.name for node in config.seed_taxonomy().categories})

    def test_old_schema_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            AppConfig.model_validate(
                {
                    "state_dir": "~/.local/state/what-am-i-doing",
                    "fallback_category": "unknown",
                }
            )

    def test_interpolate_text_uses_known_variables(self) -> None:
        rendered = interpolate_text("Tasks: ${sp_today_tasks}; Mode: ${work_mode}", {
            "sp_today_tasks": "Fix bug",
            "work_mode": "focused",
        })
        self.assertEqual("Tasks: Fix bug; Mode: focused", rendered)


if __name__ == "__main__":
    unittest.main()
