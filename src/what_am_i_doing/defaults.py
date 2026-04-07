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
- Use the provided category definitions as top-level categories exactly as named.
- Do not invent, rename, or remove top-level categories from the provided definitions.
- For categories with predefined subcategories, include them as children with their descriptions.
- You MAY add additional subcategories under predefined ones for finer granularity (e.g., coding/debugging, browsing/social_media/twitter).
- Only reference action tools that appear in the provided action tool inventory.
- CRITICAL: Parent categories with children MUST NOT have tool_calls. Only leaf categories can have tool_calls.
- CRITICAL: If a parent has children, add a "{parent}/other" child as a catch-all for activities that don't fit specific children. The "other" child should have no tool_calls or a simple stop action.
- Use the provided icons for top-level categories. For custom subcategories you add, use a GNOME symbolic icon name that fits.
"""

CLASSIFIER_BASE_PROMPT = """You classify the current desktop event into one allowed category path.

Rules:
- Return only one allowed path exactly, or `unclassified`.
- Prefer a child path when the signal is strong.
- Prefer a matching broad top-level category over `unclassified` when the current app or title clearly fits.
- Use `unclassified` only when no allowed path is plausible.
- Do not explain your reasoning.
"""
