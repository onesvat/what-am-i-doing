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

from what_am_i_doing.config import AppConfig, build_minimal_config, load_config


class ConfigTest(unittest.TestCase):
    def test_load_config_accepts_flat_choices(self) -> None:
        yaml_text = textwrap.dedent(
            """
            version: 2
            model:
              base_url: http://localhost:11434/v1
              name: gemma
            classifier:
              instructions: |
                Prefer work/project-a when coding in that repo.
            choices:
              - path: work/project-a
                description: Main work stream
                icon: laptop-symbolic
              - path: browsing/reference
                description: Reading and lookup
            tools:
              actions: {}
            """
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml") as handle:
            handle.write(yaml_text)
            handle.flush()
            config = load_config(handle.name)

        self.assertEqual(2, config.version)
        self.assertEqual(
            ["work/project-a", "browsing/reference"],
            [choice.path for choice in config.choices],
        )
        self.assertEqual(
            {"work/project-a", "browsing/reference"},
            config.choice_registry().allowed_paths(),
        )

    def test_import_directive_loads_flat_choices(self) -> None:
        config_yaml = textwrap.dedent(
            """
            version: 2
            model:
              base_url: http://localhost:11434/v1
              name: gemma
            classifier:
              instructions: ""
            choices:
              - path: coding/review
                description: Code review
              - import: imported.yaml
            tools:
              actions:
                sp_start:
                  run: ["sp", "task", "start"]
            """
        )
        imported_yaml = textwrap.dedent(
            """
            - path: work/project-a
              description: Main work stream
              actions:
                - tool: sp_start
                  args: ["123"]
            - path: admin/inbox
              description: Inbox cleanup
            """
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            imported_path = Path(tmpdir) / "imported.yaml"
            config_path.write_text(config_yaml, encoding="utf-8")
            imported_path.write_text(imported_yaml, encoding="utf-8")

            config = load_config(config_path)

        self.assertEqual(
            ["coding/review", "work/project-a", "admin/inbox"],
            [choice.path for choice in config.choices],
        )
        self.assertEqual("sp_start", config.choices[1].actions[0].tool)

    def test_missing_import_raises(self) -> None:
        yaml_text = textwrap.dedent(
            """
            version: 2
            model:
              base_url: http://localhost:11434/v1
              name: gemma
            classifier:
              instructions: ""
            choices:
              - import: missing.yaml
            """
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml") as handle:
            handle.write(yaml_text)
            handle.flush()
            with self.assertRaises(FileNotFoundError):
                load_config(handle.name)

    def test_duplicate_choice_paths_are_rejected(self) -> None:
        with self.assertRaises(Exception):
            AppConfig.model_validate(
                {
                    "version": 2,
                    "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                    "classifier": {"instructions": ""},
                    "choices": [
                        {"path": "work/project-a"},
                        {"path": "work/project-a"},
                    ],
                }
            )

    def test_unknown_action_tool_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            AppConfig.model_validate(
                {
                    "version": 2,
                    "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                    "classifier": {"instructions": ""},
                    "choices": [
                        {
                            "path": "work/project-a",
                            "actions": [{"tool": "missing_tool", "args": []}],
                        }
                    ],
                    "tools": {"actions": {}},
                }
            )

    def test_reserved_choice_path_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            AppConfig.model_validate(
                {
                    "version": 2,
                    "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                    "classifier": {"instructions": ""},
                    "choices": [{"path": "unknown"}],
                }
            )

    def test_build_minimal_config_is_version_two_and_empty(self) -> None:
        config = build_minimal_config(
            base_url="http://localhost:11434/v1",
            model_name="gemma3:4b",
            api_key_env="OPENAI_API_KEY",
        )

        self.assertEqual(2, config.version)
        self.assertEqual([], config.choices)
        self.assertEqual({}, config.tools.actions)

if __name__ == "__main__":
    unittest.main()
