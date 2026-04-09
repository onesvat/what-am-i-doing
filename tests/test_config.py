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
                        {"name": "learning"},
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
                    name="writing",
                    description="Writing work",
                    icon="📚",
                ),
            ]
        )
        normalized = config.normalize_generated_taxonomy(taxonomy)
        self.assertEqual(
            ["coding", "learning", "idle"],
            [node.name for node in normalized.categories],
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
                "model": {"base_url": "http://localhost:11434/v1", "name": "test"},
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
        coding_node = normalized.categories[0]
        self.assertEqual([], coding_node.children)
        self.assertEqual(["sp_stop"], [c.tool for c in coding_node.tool_calls])

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

    def test_config_accepts_idle_threshold_seconds(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
                "idle_threshold_seconds": 90,
            }
        )
        self.assertEqual(90, config.idle_threshold_seconds)

    def test_config_defaults_idle_threshold_to_60(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
            }
        )
        self.assertEqual(60, config.idle_threshold_seconds)

    def test_config_accepts_classify_idle_bool(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
                "classify_idle": False,
            }
        )
        self.assertEqual(False, config.classify_idle)

    def test_config_defaults_classify_idle_to_true(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
            }
        )
        self.assertEqual(True, config.classify_idle)

    def test_normalize_injects_idle_category(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="coding", description="Coding")]
        )
        normalized = config.normalize_generated_taxonomy(taxonomy)
        names = [node.name for node in normalized.categories]
        self.assertIn("idle", names)
        idle_node = next(node for node in normalized.categories if node.name == "idle")
        self.assertEqual(
            "User is idle (no keyboard/mouse activity)", idle_node.description
        )
        self.assertEqual("system-suspend-symbolic", idle_node.icon)

    def test_normalize_keeps_existing_idle_if_present(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="idle",
                    description="Custom idle description",
                    icon="custom-icon",
                ),
                TaxonomyNode(name="coding", description="Coding"),
            ]
        )
        normalized = config.normalize_generated_taxonomy(taxonomy)
        idle_node = next(node for node in normalized.categories if node.name == "idle")
        self.assertEqual("Custom idle description", idle_node.description)
        self.assertEqual("custom-icon", idle_node.icon)

    def test_idle_in_allowed_paths(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="coding", description="Coding")]
        )
        normalized = config.normalize_generated_taxonomy(taxonomy)
        self.assertIn("idle", normalized.allowed_paths())

    def test_category_path_with_subcategory_accepted(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {
                    "categories": [{"name": "communication/email"}],
                    "instructions": "",
                },
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = config.seed_taxonomy()
        self.assertEqual(["communication"], [node.name for node in taxonomy.categories])
        self.assertEqual(
            ["email"],
            [child.name for child in taxonomy.categories[0].children],
        )

    def test_reserved_category_in_path_rejected(self) -> None:
        with self.assertRaises(Exception):
            AppConfig.model_validate(
                {
                    "version": 1,
                    "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                    "generator": {
                        "categories": [{"name": "coding/unknown"}],
                        "instructions": "",
                    },
                    "classifier": {"instructions": ""},
                }
            )

    def test_browsing_does_not_expand_in_seed_taxonomy(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {
                    "categories": [{"name": "browsing"}],
                    "instructions": "",
                },
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = config.seed_taxonomy()
        self.assertEqual(["browsing"], [node.name for node in taxonomy.categories])
        self.assertEqual(
            [
                "social_media",
                "shopping",
                "news",
                "entertainment",
                "reference",
                "other",
            ],
            [child.name for child in taxonomy.categories[0].children],
        )

    def test_selectable_category_stays_top_level(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {
                    "categories": [{"name": "communication"}],
                    "instructions": "",
                },
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = config.seed_taxonomy()
        self.assertEqual(["communication"], [node.name for node in taxonomy.categories])
        self.assertEqual(
            ["email", "chat", "meeting", "other"],
            [child.name for child in taxonomy.categories[0].children],
        )

    def test_catalog_icon_used_for_category(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {
                    "categories": [{"name": "coding"}],
                    "instructions": "",
                },
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = config.seed_taxonomy()
        self.assertEqual("laptop-symbolic", taxonomy.categories[0].icon)

    def test_catalog_description_used_for_category(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {
                    "categories": [{"name": "coding"}],
                    "instructions": "",
                },
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = config.seed_taxonomy()
        self.assertIn("Software development", taxonomy.categories[0].description)

    def test_catalog_note_is_appended_for_known_category(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {
                    "categories": [
                        {
                            "name": "coding",
                            "note": "Includes technical browser work for active projects.",
                        }
                    ],
                    "instructions": "",
                },
                "classifier": {"instructions": ""},
            }
        )

        taxonomy = config.seed_taxonomy()
        self.assertIn(
            "Includes technical browser work for active projects.",
            taxonomy.categories[0].description,
        )

    def test_normalize_child_with_full_path_strips_prefix(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "coding"}], "instructions": ""},
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="coding",
                    description="Coding work",
                    children=[
                        TaxonomyNode(
                            name="coding/debugging",
                            description="Debugging work",
                        )
                    ],
                )
            ]
        )
        normalized = config.normalize_generated_taxonomy(taxonomy)
        allowed = normalized.allowed_paths()
        self.assertIn("coding/debugging", allowed)
        self.assertNotIn("coding/coding/debugging", allowed)
        coding_node = next(n for n in normalized.categories if n.name == "coding")
        self.assertEqual(["debugging", "other"], [c.name for c in coding_node.children])

    def test_normalize_repairs_top_level_browsing_slash_nodes(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "browsing"}], "instructions": ""},
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="browsing/social_media",
                    description="Social media",
                    icon="web-browser-symbolic",
                ),
                TaxonomyNode(
                    name="browsing/reference",
                    description="Reference",
                    icon="web-browser-symbolic",
                ),
            ]
        )

        normalized = config.normalize_generated_taxonomy(taxonomy)

        self.assertEqual(["browsing", "idle"], [node.name for node in normalized.categories])
        browsing = normalized.categories[0]
        self.assertEqual(
            ["social_media", "reference", "other"],
            [child.name for child in browsing.children],
        )
        self.assertIn("browsing/social_media", normalized.allowed_paths())
        self.assertIn("browsing/reference", normalized.allowed_paths())
        self.assertIn("browsing/other", normalized.allowed_paths())

    def test_normalize_child_only_seed_keeps_selected_child_without_other(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {
                    "categories": [{"name": "communication/email"}],
                    "instructions": "",
                },
                "classifier": {"instructions": ""},
            }
        )

        normalized = config.normalize_generated_taxonomy(Taxonomy(categories=[]))

        self.assertEqual(
            {"communication/email", "idle"},
            normalized.allowed_paths(),
        )
        self.assertNotIn("communication/other", normalized.allowed_paths())

    def test_normalized_browsing_path_resolves_without_key_error(self) -> None:
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"categories": [{"name": "browsing"}], "instructions": ""},
                "classifier": {"instructions": ""},
            }
        )
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="browsing/reference",
                    description="Reference",
                    icon="web-browser-symbolic",
                )
            ]
        )

        normalized = config.normalize_generated_taxonomy(taxonomy)
        top, child = normalized.node_for_path("browsing/reference")

        self.assertEqual("browsing", top.name)
        self.assertIsNotNone(child)
        self.assertEqual("reference", child.name)

    def test_normalize_generated_taxonomy_enforces_all_config_categories(self) -> None:
        """ALL categories from config must appear in normalized taxonomy."""
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "test"},
                "generator": {
                    "categories": [
                        {"name": "coding"},
                        {"name": "communication"},
                        {"name": "custom_cat", "note": "My custom category"},
                        {"name": "learning"},
                    ],
                    "instructions": "",
                },
                "classifier": {"instructions": ""},
            }
        )

        sparse_taxonomy = Taxonomy.model_validate(
            {"categories": [{"name": "coding", "description": "...", "icon": "..."}]}
        )

        normalized = config.normalize_generated_taxonomy(sparse_taxonomy)

        paths = normalized.allowed_paths()
        self.assertIn("coding", paths)
        self.assertIn("communication/other", paths)
        self.assertIn("custom_cat", paths)
        self.assertIn("learning", paths)
        self.assertIn("idle", paths)

        custom_node = next(n for n in normalized.categories if n.name == "custom_cat")
        self.assertEqual("My custom category", custom_node.description)


    def test_normalized_taxonomy_has_other_fallback_for_top_level(self) -> None:
        """Top-level categories with predefined subcategories should have '{category}/other' fallback subcategory."""
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "test"},
                "generator": {
                    "categories": [{"name": "communication"}],
                    "instructions": "",
                },
                "classifier": {"instructions": ""},
            }
        )

        simple_taxonomy = Taxonomy.model_validate(
            {
                "categories": [
                    {
                        "name": "communication",
                        "description": "...",
                        "icon": "...",
                        "children": [],
                    }
                ]
            }
        )

        normalized = config.normalize_generated_taxonomy(simple_taxonomy)

        paths = normalized.allowed_paths()
        self.assertIn("communication/other", paths)


if __name__ == "__main__":
    unittest.main()
