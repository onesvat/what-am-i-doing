from __future__ import annotations

import asyncio
from base64 import b64encode
import sys
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from waid.classifier import EventClassifier
from waid.config import AppConfig
from waid.constants import UNKNOWN_PATH
from waid.models import (
    ClassificationResult,
    ProviderState,
    SelectionCatalog,
    WindowInfo,
    utcnow,
)


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[list[dict[str, Any]]] = []

    def chat(self, _model, messages, *, json_mode=False, max_tokens=None) -> str:
        self.calls.append(messages)
        return self.responses.pop(0)


class ClassifierTest(unittest.TestCase):
    def test_retry_then_fallback_to_unknown(self) -> None:
        catalog = SelectionCatalog.model_validate(
            {
                "activity_entries": [
                    {"path": "coding/ide", "description": "Main work stream"},
                ],
                "task_entries": [
                    {"path": "project-a", "description": "Specific task"},
                ],
            }
        )
        config = AppConfig.model_validate(
            {
                "version": 2,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "classifier": {
                    "retry_count": 1,
                    "instructions": "Prefer project-a when the repo matches.",
                },
                "allow_activities": ["coding/ide"],
            }
        )
        state = ProviderState(timestamp=utcnow())
        client = FakeClient(["wrong", "still wrong"])
        classifier = EventClassifier(client)

        result = asyncio.run(classifier.classify(config, state, catalog, None))

        self.assertEqual(
            ClassificationResult(activity_path=UNKNOWN_PATH, task_path=None),
            result,
        )
        self.assertEqual(2, len(client.calls))
        self.assertIn("Prefer project-a", client.calls[0][0]["content"])

    def test_idle_detection_short_circuits_llm(self) -> None:
        catalog = SelectionCatalog.model_validate(
            {"activity_entries": [{"path": "coding/ide", "description": "Work"}]}
        )
        config = AppConfig.model_validate(
            {
                "version": 2,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "classifier": {"instructions": ""},
                "allow_activities": ["coding/ide"],
                "idle_threshold_seconds": 60,
                "classify_idle": True,
            }
        )
        state = ProviderState(timestamp=utcnow(), idle_time_seconds=120)
        client = FakeClient([])
        classifier = EventClassifier(client)

        result = asyncio.run(classifier.classify(config, state, catalog, None))

        self.assertEqual(
            ClassificationResult(activity_path="idle", task_path=None), result
        )
        self.assertEqual([], client.calls)

    def test_prompt_lists_activities_tasks_and_unknown(self) -> None:
        catalog = SelectionCatalog.model_validate(
            {
                "activity_entries": [
                    {"path": "coding/ide", "description": "Main work stream"},
                    {"path": "browsing/other", "description": "Reading"},
                ],
                "task_entries": [
                    {"path": "project-a", "description": "Specific task context"},
                ],
            }
        )
        config = AppConfig.model_validate(
            {
                "version": 2,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "classifier": {"instructions": ""},
                "allow_activities": ["coding/ide", "browsing/other"],
            }
        )
        state = ProviderState(
            timestamp=utcnow(),
            focused_window=WindowInfo(title="README.md", wm_class="code"),
        )
        client = FakeClient(
            ['{"activity_path":"coding/ide","task_path":"project-a"}']
        )
        classifier = EventClassifier(client)

        result = asyncio.run(
            classifier.classify(
                config,
                state,
                catalog,
                ClassificationResult(activity_path="browsing/other", task_path=None),
            )
        )

        self.assertEqual(
            ClassificationResult(activity_path="coding/ide", task_path="project-a"),
            result,
        )
        prompt = client.calls[0][0]["content"]
        self.assertIn("Allowed activity_path values:", prompt)
        self.assertIn("- coding/ide: Main work stream", prompt)
        self.assertIn("- browsing/other: Reading", prompt)
        self.assertIn("- project-a: Specific task context", prompt)
        self.assertIn(f"- {UNKNOWN_PATH}", prompt)
        self.assertIn("idle", prompt)

    def test_screenshot_path_is_sent_as_vision_message(self) -> None:
        catalog = SelectionCatalog.model_validate(
            {"activity_entries": [{"path": "coding/ide", "description": "Work"}]}
        )
        config = AppConfig.model_validate(
            {
                "version": 2,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "classifier": {"instructions": ""},
                "allow_activities": ["coding/ide"],
            }
        )
        state = ProviderState(timestamp=utcnow())
        client = FakeClient(['{"activity_path":"coding/ide","task_path":null}'])
        classifier = EventClassifier(client)

        with TemporaryDirectory() as temp_dir:
            screenshot_path = Path(temp_dir) / "shot.png"
            screenshot_bytes = b"png-bytes"
            screenshot_path.write_bytes(screenshot_bytes)

            result = asyncio.run(
                classifier.classify(
                    config,
                    state,
                    catalog,
                    None,
                    screenshot_path=str(screenshot_path),
                )
            )

        self.assertEqual(ClassificationResult(activity_path="coding/ide", task_path=None), result)
        content = client.calls[0][0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual("text", content[0]["type"])
        self.assertEqual("image_url", content[1]["type"])
        self.assertEqual(
            f"data:image/png;base64,{b64encode(screenshot_bytes).decode('ascii')}",
            content[1]["image_url"]["url"],
        )


if __name__ == "__main__":
    unittest.main()
