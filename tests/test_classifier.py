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
from what_am_i_doing.constants import UNKNOWN_CHOICE_PATH
from what_am_i_doing.models import ChoiceRegistry, ProviderState, WindowInfo, utcnow


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def chat(self, _model, messages, *, json_mode=False, max_tokens=None) -> str:
        self.calls.append(messages[0]["content"])
        return self.responses.pop(0)


class ClassifierTest(unittest.TestCase):
    def test_retry_then_fallback_to_unknown(self) -> None:
        choices = ChoiceRegistry.model_validate(
            {
                "choices": [
                    {"path": "work/project-a", "description": "Main work stream"},
                ]
            }
        )
        config = AppConfig.model_validate(
            {
                "version": 2,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "classifier": {
                    "retry_count": 1,
                    "instructions": "Prefer work/project-a when the repo matches.",
                },
                "choices": [
                    {"path": "work/project-a", "description": "Main work stream"},
                ],
            }
        )
        state = ProviderState(timestamp=utcnow())
        client = FakeClient(["wrong", "still wrong"])
        classifier = EventClassifier(client)

        result = asyncio.run(classifier.classify(config, state, choices, None))

        self.assertEqual(UNKNOWN_CHOICE_PATH, result)
        self.assertEqual(2, len(client.calls))
        self.assertIn("Prefer work/project-a", client.calls[0])

    def test_idle_detection_short_circuits_llm(self) -> None:
        choices = ChoiceRegistry.model_validate(
            {"choices": [{"path": "work/project-a", "description": "Work"}]}
        )
        config = AppConfig.model_validate(
            {
                "version": 2,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "classifier": {"instructions": ""},
                "choices": [{"path": "work/project-a", "description": "Work"}],
                "idle_threshold_seconds": 60,
                "classify_idle": True,
            }
        )
        state = ProviderState(timestamp=utcnow(), idle_time_seconds=120)
        client = FakeClient([])
        classifier = EventClassifier(client)

        result = asyncio.run(classifier.classify(config, state, choices, None))

        self.assertEqual("idle", result)
        self.assertEqual([], client.calls)

    def test_prompt_lists_choices_and_unknown(self) -> None:
        choices = ChoiceRegistry.model_validate(
            {
                "choices": [
                    {"path": "work/project-a", "description": "Main work stream"},
                    {"path": "browsing/reference", "description": "Reading"},
                ]
            }
        )
        config = AppConfig.model_validate(
            {
                "version": 2,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "classifier": {"instructions": ""},
                "choices": [
                    {"path": "work/project-a", "description": "Main work stream"},
                    {"path": "browsing/reference", "description": "Reading"},
                ],
            }
        )
        state = ProviderState(
            timestamp=utcnow(),
            focused_window=WindowInfo(title="README.md", wm_class="code"),
        )
        client = FakeClient(["work/project-a"])
        classifier = EventClassifier(client)

        result = asyncio.run(
            classifier.classify(config, state, choices, "browsing/reference")
        )

        self.assertEqual("work/project-a", result)
        prompt = client.calls[0]
        self.assertIn("Available choices:", prompt)
        self.assertIn("- work/project-a: Main work stream", prompt)
        self.assertIn("- browsing/reference: Reading", prompt)
        self.assertIn(f"- {UNKNOWN_CHOICE_PATH}", prompt)
        self.assertIn("Previous path: browsing/reference", prompt)


if __name__ == "__main__":
    unittest.main()
