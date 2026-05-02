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

from waid.config import (
    AppConfig,
    build_minimal_config,
    build_selection_catalog,
    load_config,
    load_tasks,
)
from waid.activity_catalog import builtin_activity_entries
from waid.models import CatalogEntry


class ConfigTest(unittest.TestCase):
    def test_load_config_accepts_activities(self) -> None:
        yaml_text = textwrap.dedent(
            """
            version: 2
            model:
              base_url: http://localhost:11434/v1
              name: gemma
            classifier:
              instructions: |
                Prefer fix-waid when repo matches.
            activities:
              - path: custom/research
                description: Custom research
            tools:
              actions: {}
            """
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml") as handle:
            handle.write(yaml_text)
            handle.flush()
            config = load_config(handle.name)

        self.assertEqual(["custom/research"], [entry.path for entry in config.activities])
        catalog = build_selection_catalog(config, [CatalogEntry(path="fix-waid")])
        self.assertIn("browsing/social_media", catalog.activity_paths())
        self.assertIn("custom/research", catalog.activity_paths())
        self.assertEqual({"fix-waid"}, catalog.task_paths())

    def test_old_choices_schema_is_rejected(self) -> None:
        yaml_text = textwrap.dedent(
            """
            version: 2
            model:
              base_url: http://localhost:11434/v1
              name: gemma
            classifier:
              instructions: ""
            choices:
              - path: old/path
            """
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml") as handle:
            handle.write(yaml_text)
            handle.flush()
            with self.assertRaises(Exception):
                load_config(handle.name)

    def test_inline_tasks_schema_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            AppConfig.model_validate(
                {
                    "version": 2,
                    "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                    "classifier": {"instructions": ""},
                    "tasks": [{"path": "fix-waid"}],
                }
            )

    def test_allow_and_block_overlap_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            AppConfig.model_validate(
                {
                    "version": 2,
                    "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                    "classifier": {"instructions": ""},
                    "allow_activities": ["browsing/other"],
                    "block_activities": ["browsing/other"],
                }
            )

    def test_custom_activity_cannot_override_builtin(self) -> None:
        with self.assertRaises(Exception):
            AppConfig.model_validate(
                {
                    "version": 2,
                    "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                    "classifier": {"instructions": ""},
                    "activities": [{"path": "browsing/other"}],
                }
            )

    def test_unknown_action_tool_is_rejected_in_tasks_file(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 2,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "classifier": {"instructions": ""},
                "tools": {"actions": {}},
            }
        )
        with self.assertRaises(Exception):
            build_selection_catalog(
                config,
                [CatalogEntry(path="fix-waid", actions=[{"tool": "missing_tool"}])],
            )

    def test_reserved_task_path_is_rejected(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml") as handle:
            handle.write("- path: unknown\n")
            handle.flush()
            with self.assertRaises(Exception):
                load_tasks(handle.name)

    def test_build_minimal_config_is_version_two_and_empty(self) -> None:
        config = build_minimal_config(
            base_url="http://localhost:11434/v1",
            model_name="gemma3:4b",
            api_key_env="OPENAI_API_KEY",
        )

        self.assertEqual(2, config.version)
        self.assertEqual([], config.activities)
        self.assertEqual({}, config.tools.actions)

    def test_builtin_activity_catalog_matches_expected_paths(self) -> None:
        self.assertEqual(
            [
                "browsing/social_media",
                "browsing/shopping",
                "browsing/llm",
                "browsing/research",
                "browsing/news",
                "browsing/other",
                "coding/ide",
                "coding/terminal",
                "communication/chat",
                "communication/email",
                "communication/meetings",
                "communication/other",
                "admin",
                "writing",
                "learning",
                "media/video",
                "media/audio",
                "media/other",
                "system",
                "gaming",
                "adult",
            ],
            [entry.path for entry in builtin_activity_entries()],
        )


if __name__ == "__main__":
    unittest.main()
