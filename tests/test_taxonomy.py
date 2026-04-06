from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.models import Taxonomy, TaxonomyNode, ToolCall


class TaxonomyTest(unittest.TestCase):
    def test_allowed_paths_only_leaves(self) -> None:
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="coding",
                    description="Coding work",
                    tool_calls=[ToolCall(tool="ha", args=["coding"])],
                    children=[
                        TaxonomyNode(
                            name="project-x",
                            description="Project X",
                            tool_calls=[ToolCall(tool="sp_switch", args=["123"])],
                        )
                    ],
                ),
                TaxonomyNode(
                    name="learning",
                    description="Learning work",
                    tool_calls=[ToolCall(tool="ha", args=["learning"])],
                    children=[],
                ),
            ]
        )
        self.assertEqual({"coding/project-x", "learning"}, taxonomy.allowed_paths())

    def test_tools_for_child_path_no_parent_inheritance(self) -> None:
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="coding",
                    description="Coding work",
                    tool_calls=[ToolCall(tool="ha", args=["coding"])],
                    children=[
                        TaxonomyNode(
                            name="project-x",
                            description="Project X",
                            tool_calls=[ToolCall(tool="sp_switch", args=["123"])],
                        )
                    ],
                )
            ]
        )
        calls = taxonomy.tools_for_path("coding/project-x")
        self.assertEqual(["sp_switch"], [call.tool for call in calls])

    def test_tools_for_leaf_parent(self) -> None:
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="learning",
                    description="Learning work",
                    tool_calls=[ToolCall(tool="ha", args=["learning"])],
                    children=[],
                )
            ]
        )
        calls = taxonomy.tools_for_path("learning")
        self.assertEqual(["ha"], [call.tool for call in calls])

    def test_rejects_unknown_action_tool_reference(self) -> None:
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(
                    name="coding",
                    description="Coding work",
                    tool_calls=[ToolCall(tool="ha", args=["coding"])],
                )
            ]
        )
        with self.assertRaises(ValueError):
            taxonomy.validate_action_tool_refs({"sp_switch"})


if __name__ == "__main__":
    unittest.main()
