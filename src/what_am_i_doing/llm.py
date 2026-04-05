from __future__ import annotations

import json
import os
from typing import Any
from urllib import request

from .config import ModelConfig


class LLMError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def chat(
        self,
        model: ModelConfig,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model.name,
            "messages": messages,
            "temperature": model.temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = json.dumps(payload).encode("utf-8")
        endpoint = model.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = os.environ.get(model.api_key_env, "").strip() if model.api_key_env else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = request.Request(endpoint, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=model.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
        except Exception as exc:  # pragma: no cover - exercised in integration
            raise LLMError(str(exc)) from exc
        try:
            parsed = json.loads(body)
            content = parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMError(f"invalid llm response: {body}") from exc
        if not isinstance(content, str):
            raise LLMError("llm content is not a string")
        return content.strip()
