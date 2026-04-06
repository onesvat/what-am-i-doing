from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.classifier import EventClassifier
from what_am_i_doing.config import AppConfig
from what_am_i_doing.models import ProviderState, Taxonomy, TaxonomyNode, utcnow


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def chat(self, _model, messages, *, json_mode=False, max_tokens=None) -> str:
        self.calls.append(messages[0]["content"])
        return self.responses.pop(0)


class ClassifierTest(unittest.TestCase):
    def test_retry_then_fallback(self) -> None:
        taxonomy = Taxonomy(categories=[TaxonomyNode(name="coding", description="Coding work")])
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"instructions": "gen"},
                "classifier": {
                    "retry_count": 1,
                    "instructions": "Mode: ${work_mode}",
                    "params": {"work_mode": "focused"},
                },
            }
        )
        state = ProviderState(timestamp=utcnow())
        client = FakeClient(["wrong", "still wrong"])
        classifier = EventClassifier(client)
        result = asyncio.run(classifier.classify(config, state, taxonomy, None))
        self.assertEqual("unclassified", result)
        self.assertEqual(2, len(client.calls))
        self.assertIn("Mode: focused", client.calls[0])


if __name__ == "__main__":
    unittest.main()
