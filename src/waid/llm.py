from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request

from .config import ModelConfig
from .debug import DebugLogger


class LLMError(RuntimeError):
    pass


def build_vision_message(text: str, image_base64: str, media_type: str = "image/png") -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{image_base64}"},
            },
        ],
    }


class OpenAICompatibleClient:
    def __init__(self, debug: DebugLogger | None = None) -> None:
        self.debug = debug

    def chat(
        self,
        model: ModelConfig,
        messages: list[dict[str, Any]],
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
            payload["response_format"] = self._json_response_format()
        data = json.dumps(payload).encode("utf-8")
        endpoint = model.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = model.api_key.strip() or (os.environ.get(model.api_key_env, "").strip() if model.api_key_env else "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if self.debug is not None:
            self.debug.log(
                "llm_request",
                model=model.name,
                endpoint=endpoint,
                json_mode=json_mode,
                max_tokens=max_tokens,
                messages=messages,
            )
        req = request.Request(endpoint, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=model.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
        except error.HTTPError as exc:  # pragma: no cover - exercised in integration
            body = exc.read().decode("utf-8", errors="replace")
            if self.debug is not None:
                self.debug.log(
                    "llm_error",
                    model=model.name,
                    endpoint=endpoint,
                    error=str(exc),
                    body=body,
                )
            raise LLMError(f"{exc}: {body}") from exc
        except Exception as exc:  # pragma: no cover - exercised in integration
            if self.debug is not None:
                self.debug.log("llm_error", model=model.name, endpoint=endpoint, error=str(exc))
            raise LLMError(str(exc)) from exc
        try:
            parsed = json.loads(body)
            content = parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            if self.debug is not None:
                self.debug.log("llm_response_raw", model=model.name, body=body)
            raise LLMError(f"invalid llm response: {body}") from exc
        if not isinstance(content, str):
            raise LLMError("llm content is not a string")
        if self.debug is not None:
            self.debug.log("llm_response", model=model.name, content=content.strip())
        return content.strip()

    def _json_response_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "waid_response",
                "strict": False,
                "schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                },
            },
        }
