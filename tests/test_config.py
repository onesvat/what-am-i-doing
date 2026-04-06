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
from what_am_i_doing.models import Taxonomy, TaxonomyNode


class ConfigTest(unittest.TestCase):
    def test_load_config_preserves_only_user_categories(self) -> None:
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
        self.assertEqual({"coding"}, {node.name for node in config.seed_taxonomy().categories})

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

    def test_normalize_generated_taxonomy_keeps_seed_top_levels(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {
                    "categories": [
                        {"name": "coding"},
                        {"name": "surfing"},
                    ],
                    "instructions": "gen",
                },
                "classifier": {"instructions": "cls"},
            }
        )
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="coding",
                    description="Coding work",
                    icon="💻",
                    children=[
                        TaxonomyNode(name="project-x", description="Project X"),
                    ],
                ),
                TaxonomyNode(
                    name="research",
                    description="Research work",
                    icon="📚",
                ),
            ]
        )
        normalized = config.normalize_generated_taxonomy(taxonomy)
        self.assertEqual(["coding", "surfing"], [node.name for node in normalized.categories])
        self.assertEqual("laptop-symbolic", normalized.categories[0].icon)
        self.assertEqual("project-x", normalized.categories[0].children[0].name)


if __name__ == "__main__":
    unittest.main()
