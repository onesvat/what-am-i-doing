from __future__ import annotations

from dataclasses import dataclass

from prompt_toolkit import prompt


@dataclass(slots=True)
class InitAnswers:
    base_url: str
    model_name: str
    api_key_env: str


def run_init_wizard() -> InitAnswers:
    return InitAnswers(
        base_url=prompt(
            "Model base URL: ", default="http://localhost:11434/v1"
        ).strip(),
        model_name=prompt("Model name: ", default="gemma3:4b").strip(),
        api_key_env=prompt("API key env var: ", default="OPENAI_API_KEY").strip(),
    )
