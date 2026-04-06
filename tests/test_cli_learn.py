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
    LearnedRule,
    WindowExample,
    load_config,
    parse_target_from_hint,
    render_config,
    save_config,
)


class LearnCommandTest(unittest.TestCase):
    def test_parse_hint_extracts_coding_other(self) -> None:
        hint = "opencode window without anything should be coding/other"
        target = parse_target_from_hint(hint)
        self.assertEqual("coding/other", target)

    def test_parse_hint_extracts_coding_editing(self) -> None:
        hint = "vim terminal should be coding/editing"
        target = parse_target_from_hint(hint)
        self.assertEqual("coding/editing", target)

    def test_parse_hint_extracts_single_category(self) -> None:
        hint = "email client should be messaging"
        target = parse_target_from_hint(hint)
        self.assertEqual("messaging", target)

    def test_learned_rule_creation_with_window_example(self) -> None:
        rule = LearnedRule(
            hint="opencode window should be coding/other",
            target="coding/other",
            window_example=WindowExample(
                wm_class="opencode",
                title="",
                app_id="opencode",
                workspace_name="code",
            ),
        )
        self.assertEqual("coding/other", rule.target)
        self.assertEqual("opencode", rule.window_example.wm_class)

    def test_config_add_learned_rule_and_save(self) -> None:
        yaml_text = textwrap.dedent(
            """
            version: 1
            model:
              base_url: http://localhost:11434/v1
              name: gemma
            generator:
              categories:
                - name: coding
              instructions: ""
            classifier:
              instructions: ""
            """
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=False) as handle:
            handle.write(yaml_text)
            handle.flush()
            config_path = handle.name

        config = load_config(config_path)
        rule = LearnedRule(
            hint="opencode window should be coding/other",
            target="coding/other",
        )
        config.learned.append(rule)
        save_config(config_path, config)

        updated_yaml = Path(config_path).read_text()
        self.assertIn("learned:", updated_yaml)
        self.assertIn("coding/other", updated_yaml)


if __name__ == "__main__":
    unittest.main()
