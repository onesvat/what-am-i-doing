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
- Build a small practical taxonomy for the current day.
- Use the provided broad category hints as the top-level categories exactly as named.
- Do not invent, rename, or remove top-level categories from the hints.
- Only reference action tools that appear in the provided action tool inventory.
- Keep top-level categories broad and add children only when they are useful for real actions.
- Use GNOME icon names like `laptop-symbolic`, not emoji.
"""

CLASSIFIER_BASE_PROMPT = """You classify the current desktop event into one allowed category path.

Rules:
- Return only one allowed path exactly, or `unclassified`.
- Prefer a child path when the signal is strong.
- Prefer a matching broad top-level category over `unclassified` when the current app or title clearly fits.
- Use `unclassified` only when no allowed path is plausible.
- Do not explain your reasoning.
"""
