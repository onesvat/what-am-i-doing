from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.config import AppConfig
from what_am_i_doing.generator import TaxonomyGenerator


class GeneratorPromptTest(unittest.TestCase):
    def test_prompt_canonicalizes_child_only_seed_to_parent_with_child(self) -> None:
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

        prompt = TaxonomyGenerator(client=None)._build_prompt(config, {}, "")  # type: ignore[arg-type]

        self.assertIn("- communication (icon: mail-unread-symbolic):", prompt)
        self.assertIn("Subcategories: email.", prompt)
        self.assertNotIn("- communication/email:", prompt)

    def test_prompt_marks_empty_action_inventory(self) -> None:
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

        prompt = TaxonomyGenerator(client=None)._build_prompt(config, {}, "")  # type: ignore[arg-type]

        self.assertIn("Action tool inventory:\n- none", prompt)


if __name__ == "__main__":
    unittest.main()
