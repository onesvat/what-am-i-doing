from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "sp-generate-tasks.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("sp_generate_tasks", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("sp_generate_tasks", module)
    spec.loader.exec_module(module)
    return module


mod = _load_script_module()


class GeneratorScriptTest(unittest.TestCase):
    def test_slugify_transliterates_turkish_characters(self) -> None:
        self.assertEqual(
            "code-ve-projeleri-gozden-gecir",
            mod.slugify("Code ve Projeleri gözden geçir"),
        )

    def test_build_task_entries_keeps_plain_task_paths(self) -> None:
        class FakeLLM:
            def chat(self, *_args, **_kwargs):
                return "Task description"

        class FakeConfig:
            classifier_model = object()

        original = mod.OpenAICompatibleClient
        mod.OpenAICompatibleClient = lambda: FakeLLM()
        try:
            tasks = mod.build_task_entries(
                [
                    {"id": "1", "title": "Dailies"},
                    {"id": "2", "title": "Fix waid"},
                ],
                config=FakeConfig(),
            )
        finally:
            mod.OpenAICompatibleClient = original

        self.assertEqual("dailies", tasks[0]["path"])
        self.assertEqual("fix-waid", tasks[1]["path"])
        self.assertEqual([{"tool": "sp_start", "args": ["1"]}], tasks[0]["actions"])


if __name__ == "__main__":
    unittest.main()
