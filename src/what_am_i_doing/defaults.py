from __future__ import annotations


DEFAULT_CATEGORY_CHOICES: list[tuple[str, str]] = [
    ("coding", ""),
    ("messaging", "email, chat, meetings"),
    ("planning", ""),
    ("surfing", ""),
]

GENERATOR_BASE_PROMPT = """You generate the runtime activity taxonomy for a GNOME desktop tracker.

Rules:
- Return valid JSON only.
- Use this exact schema:
  {"categories":[{"name":"...","description":"...","icon":"...","tool_calls":[{"tool":"...","args":["..."]}],"children":[...]}]}
- Keep the fallback category `unknown`.
- Build a small practical taxonomy for the current day.
- Only reference action tools that appear in the provided action tool inventory.
- Keep top-level categories broad and add children only when they are useful for real actions.
"""

CLASSIFIER_BASE_PROMPT = """You classify the current desktop event into one allowed category path.

Rules:
- Return only one allowed path exactly.
- Prefer a child path when the signal is strong.
- Use `unknown` when unclear.
- Do not explain your reasoning.
"""
