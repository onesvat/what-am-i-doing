from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from waid.llm import OpenAICompatibleClient


class LLMClientTest(unittest.TestCase):
    def test_json_mode_uses_json_schema_response_format(self) -> None:
        client = OpenAICompatibleClient()
        payload = client._json_response_format()
        self.assertEqual("json_schema", payload["type"])
        self.assertEqual("waid_response", payload["json_schema"]["name"])
        self.assertEqual("object", payload["json_schema"]["schema"]["type"])
        self.assertTrue(payload["json_schema"]["schema"]["additionalProperties"])

    def test_json_response_format_is_json_serializable(self) -> None:
        client = OpenAICompatibleClient()
        text = json.dumps(client._json_response_format())
        self.assertIn("json_schema", text)


if __name__ == "__main__":
    unittest.main()
