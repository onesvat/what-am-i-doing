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

from what_am_i_doing.config import (
    AppConfig,
    LearnedRule,
    WindowExample,
    interpolate_text,
    load_config,
    parse_target_from_hint,
)
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
        self.assertEqual(
            {"coding"}, {node.name for node in config.seed_taxonomy().categories}
        )

    def test_old_schema_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            AppConfig.model_validate(
                {
                    "state_dir": "~/.local/state/what-am-i-doing",
                    "fallback_category": "unknown",
                }
            )

    def test_interpolate_text_uses_known_variables(self) -> None:
        rendered = interpolate_text(
            "Tasks: ${sp_today_tasks}; Mode: ${work_mode}",
            {
                "sp_today_tasks": "Fix bug",
                "work_mode": "focused",
            },
        )
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
        self.assertEqual(
            ["coding", "surfing"], [node.name for node in normalized.categories]
        )
        self.assertEqual("laptop-symbolic", normalized.categories[0].icon)
        self.assertEqual("project-x", normalized.categories[0].children[0].name)

    def test_normalize_clears_parent_tool_calls_when_has_children(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
                "tools": {"actions": {"sp_stop": {"run": ["stop"]}}},
            }
        )
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="coding",
                    description="Coding",
                    tool_calls=[{"tool": "sp_stop", "args": []}],
                    children=[
                        TaxonomyNode(name="project-x", description="X"),
                    ],
                ),
            ]
        )
        normalized = config.normalize_generated_taxonomy(taxonomy)
        self.assertEqual([], normalized.categories[0].tool_calls)

    def test_normalize_adds_other_child_when_missing(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
                "tools": {"actions": {"sp_stop": {"run": ["stop"]}}},
            }
        )
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="coding",
                    description="Coding",
                    tool_calls=[{"tool": "sp_stop", "args": []}],
                    children=[
                        TaxonomyNode(name="project-x", description="X"),
                    ],
                ),
            ]
        )
        normalized = config.normalize_generated_taxonomy(taxonomy)
        child_names = [c.name for c in normalized.categories[0].children]
        self.assertIn("other", child_names)
        other_child = next(
            c for c in normalized.categories[0].children if c.name == "other"
        )
        self.assertEqual(["sp_stop"], [c.tool for c in other_child.tool_calls])

    def test_normalize_keeps_parent_tool_calls_when_no_children(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
                "tools": {"actions": {"sp_stop": {"run": ["stop"]}}},
            }
        )
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="coding",
                    description="Coding",
                    tool_calls=[{"tool": "sp_stop", "args": []}],
                    children=[],
                ),
            ]
        )
        normalized = config.normalize_generated_taxonomy(taxonomy)
        self.assertEqual(
            ["sp_stop"], [c.tool for c in normalized.categories[0].tool_calls]
        )

    def test_normalize_inherits_parent_tools_to_existing_other(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
                "tools": {"actions": {"sp_stop": {"run": ["stop"]}}},
            }
        )
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="coding",
                    description="Coding",
                    tool_calls=[{"tool": "sp_stop", "args": []}],
                    children=[
                        TaxonomyNode(name="project-x", description="X"),
                        TaxonomyNode(
                            name="other", description="Other coding", tool_calls=[]
                        ),
                    ],
                ),
            ]
        )
        normalized = config.normalize_generated_taxonomy(taxonomy)
        other_child = next(
            c for c in normalized.categories[0].children if c.name == "other"
        )
        self.assertEqual(["sp_stop"], [c.tool for c in other_child.tool_calls])

    def test_config_accepts_empty_learned_section(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
                "learned": [],
            }
        )
        self.assertEqual([], config.learned)

    def test_config_accepts_learned_rules_with_hint_and_target(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
                "learned": [
                    {
                        "hint": "opencode window should be coding/other",
                        "target": "coding/other",
                    }
                ],
            }
        )
        self.assertEqual(1, len(config.learned))
        self.assertEqual(
            "opencode window should be coding/other", config.learned[0].hint
        )
        self.assertEqual("coding/other", config.learned[0].target)

    def test_learned_rule_can_have_window_example(self) -> None:
        rule = LearnedRule.model_validate(
            {
                "hint": "opencode window should be coding/other",
                "target": "coding/other",
                "window_example": {
                    "wm_class": "opencode",
                    "title": "",
                    "app_id": "opencode",
                    "workspace_name": "code",
                },
            }
        )
        self.assertIsNotNone(rule.window_example)
        self.assertEqual("opencode", rule.window_example.wm_class)
        self.assertEqual("", rule.window_example.title)

    def test_learned_rule_target_must_be_valid_path_format(self) -> None:
        with self.assertRaises(Exception):
            LearnedRule.model_validate(
                {
                    "hint": "test",
                    "target": "",
                }
            )
        with self.assertRaises(Exception):
            LearnedRule.model_validate(
                {
                    "hint": "test",
                    "target": "coding/",
                }
            )
        with self.assertRaises(Exception):
            LearnedRule.model_validate(
                {
                    "hint": "test",
                    "target": "/other",
                }
            )

    def test_parse_target_from_hint_extracts_path(self) -> None:
        target = parse_target_from_hint(
            "opencode window without anything should be coding/other"
        )
        self.assertEqual("coding/other", target)

    def test_parse_target_from_hint_raises_on_invalid_format(self) -> None:
        with self.assertRaises(ValueError):
            parse_target_from_hint("opencode window is cool")


if __name__ == "__main__":
    unittest.main()
