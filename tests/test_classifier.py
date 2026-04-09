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
from what_am_i_doing.models import ProviderState, Taxonomy, TaxonomyNode, WindowInfo, utcnow


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def chat(self, _model, messages, *, json_mode=False, max_tokens=None) -> str:
        self.calls.append(messages[0]["content"])
        return self.responses.pop(0)


class ClassifierTest(unittest.TestCase):
    def test_retry_then_fallback(self) -> None:
        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="coding", description="Coding work")]
        )
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

    def test_idle_detection_above_threshold(self) -> None:
        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="idle", description="User idle")]
        )
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"instructions": "gen"},
                "classifier": {"instructions": "cls"},
                "idle_threshold_seconds": 60,
                "classify_idle": True,
            }
        )
        state = ProviderState(timestamp=utcnow(), idle_time_seconds=120)
        client = FakeClient([])
        classifier = EventClassifier(client)
        result = asyncio.run(classifier.classify(config, state, taxonomy, None))
        self.assertEqual("idle", result)
        self.assertEqual(0, len(client.calls))

    def test_idle_detection_exactly_at_threshold(self) -> None:
        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="idle", description="User idle")]
        )
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"instructions": "gen"},
                "classifier": {"instructions": "cls"},
                "idle_threshold_seconds": 60,
                "classify_idle": True,
            }
        )
        state = ProviderState(timestamp=utcnow(), idle_time_seconds=60)
        client = FakeClient([])
        classifier = EventClassifier(client)
        result = asyncio.run(classifier.classify(config, state, taxonomy, None))
        self.assertEqual("idle", result)

    def test_idle_detection_below_threshold(self) -> None:
        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="coding", description="Coding")]
        )
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"instructions": "gen"},
                "classifier": {"instructions": "cls"},
                "idle_threshold_seconds": 60,
                "classify_idle": True,
            }
        )
        state = ProviderState(timestamp=utcnow(), idle_time_seconds=30)
        client = FakeClient(["coding"])
        classifier = EventClassifier(client)
        result = asyncio.run(classifier.classify(config, state, taxonomy, None))
        self.assertEqual("coding", result)
        self.assertEqual(1, len(client.calls))

    def test_idle_detection_disabled(self) -> None:
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(name="idle", description="User idle"),
                TaxonomyNode(name="coding", description="Coding"),
            ]
        )
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"instructions": "gen"},
                "classifier": {"instructions": "cls"},
                "idle_threshold_seconds": 60,
                "classify_idle": False,
            }
        )
        state = ProviderState(timestamp=utcnow(), idle_time_seconds=120)
        client = FakeClient(["coding"])
        classifier = EventClassifier(client)
        result = asyncio.run(classifier.classify(config, state, taxonomy, None))
        self.assertEqual("coding", result)
        self.assertEqual(1, len(client.calls))

    def test_idle_detection_no_idle_time(self) -> None:
        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="coding", description="Coding")]
        )
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"instructions": "gen"},
                "classifier": {"instructions": "cls"},
                "idle_threshold_seconds": 60,
                "classify_idle": True,
            }
        )
        state = ProviderState(timestamp=utcnow())
        client = FakeClient(["coding"])
        classifier = EventClassifier(client)
        result = asyncio.run(classifier.classify(config, state, taxonomy, None))
        self.assertEqual("coding", result)

    def test_idle_not_in_taxonomy(self) -> None:
        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="coding", description="Coding")]
        )
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"instructions": "gen"},
                "classifier": {"instructions": "cls"},
                "idle_threshold_seconds": 60,
                "classify_idle": True,
            }
        )
        state = ProviderState(timestamp=utcnow(), idle_time_seconds=120)
        client = FakeClient(["coding"])
        classifier = EventClassifier(client)
        result = asyncio.run(classifier.classify(config, state, taxonomy, None))
        self.assertEqual("coding", result)

    def test_idle_not_in_llm_allowed_outputs(self) -> None:
        taxonomy = Taxonomy(
            categories=[
                TaxonomyNode(name="coding", description="Coding"),
                TaxonomyNode(name="idle", description="User idle"),
            ]
        )
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"instructions": "gen"},
                "classifier": {"instructions": "cls"},
                "idle_threshold_seconds": 60,
                "classify_idle": True,
            }
        )
        state = ProviderState(timestamp=utcnow(), idle_time_seconds=30)
        client = FakeClient(["coding"])
        classifier = EventClassifier(client)
        result = asyncio.run(classifier.classify(config, state, taxonomy, None))
        self.assertEqual("coding", result)
        prompt = client.calls[0]
        allowed_section = prompt.split("Allowed outputs:")[1].split(
            "Taxonomy details:"
        )[0]
        self.assertIn("- coding", allowed_section)
        self.assertIn("- unclassified", allowed_section)
        self.assertNotIn("idle", allowed_section)
        taxonomy_section = prompt.split("Taxonomy details:")[1].split("Previous path:")[
            0
        ]
        self.assertIn("coding:", taxonomy_section)
        self.assertNotIn("idle:", taxonomy_section)

    def test_prompt_includes_supporting_windows(self) -> None:
        taxonomy = Taxonomy(
            categories=[TaxonomyNode(name="coding", description="Coding work")]
        )
        config = AppConfig.model_validate(
            {
                "version": 1,
                "model": {"base_url": "http://localhost:11434/v1", "name": "g"},
                "generator": {"instructions": "gen"},
                "classifier": {"instructions": "cls"},
            }
        )
        state = ProviderState(
            timestamp=utcnow(),
            focused_window=WindowInfo(
                title="repo docs - Firefox",
                wm_class="org.mozilla.firefox",
                workspace=1,
            ),
            open_windows=[
                WindowInfo(
                    title="repo docs - Firefox",
                    wm_class="org.mozilla.firefox",
                    workspace=1,
                ),
                WindowInfo(
                    title="app.py - Visual Studio Code",
                    wm_class="code",
                    app_id="com.visualstudio.code",
                    workspace=1,
                ),
                WindowInfo(
                    title="build.log",
                    wm_class="kitty",
                    workspace=1,
                ),
            ],
        )
        prompt = EventClassifier(client=FakeClient([]))._build_prompt(
            config,
            state,
            taxonomy,
            "coding",
            ["coding", "unclassified"],
        )

        self.assertIn("Supporting open windows:", prompt)
        self.assertIn("code: app.py - Visual Studio Code", prompt)
        self.assertIn("kitty: build.log", prompt)


if __name__ == "__main__":
    unittest.main()
