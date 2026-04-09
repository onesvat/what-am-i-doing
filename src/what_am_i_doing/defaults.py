from __future__ import annotations

GENERATOR_BASE_PROMPT = """You generate the runtime activity taxonomy for a GNOME desktop tracker.

Rules:
- Return valid JSON only.
- Use this exact schema:
  {"categories":[{"name":"...","description":"...","icon":"...","tool_calls":[{"tool":"...","args":["..."]}],"children":[...]}]}
- Build a small practical taxonomy for the current day.
- CRITICAL: You MUST include ALL provided category definitions as top-level categories. Do not omit any category from the provided definitions.
- Do not invent, rename, or add top-level categories beyond the provided definitions.
- CRITICAL: Top-level category names MUST NOT contain `/`.
- Keep top-level categories broad. Create child categories only for active projects, recurring work, or clearly distinct distractions.
- Treat `coding` as active software development, including technical browser work that directly supports the current project.
- Treat `writing` as substantial drafting or editing, not short transactional messages.
- Treat `learning` as study, courses, tutorials, educational reading, or educational video.
- Treat `communication` as email, chat, and meetings.
- Treat `admin` as task management, calendar, planning, finance, forms, and routine operations.
- Treat `browsing` as general browsing that is neither active development nor structured learning.
- Treat `media` as passive entertainment or media consumption.
- For categories with predefined subcategories, include them as children with their descriptions.
- CRITICAL: Child `name` values are local to their parent. Under `browsing`, use `reference` or `social_media/twitter`, never `browsing/reference`.
- You MAY add additional subcategories under predefined ones for finer granularity (e.g., child `debugging` under `coding`, or child `social_media/twitter` under `browsing`).
- Only reference action tools that appear in the provided action tool inventory.
- If the action tool inventory is empty, do not emit any `tool_calls`.
- CRITICAL: Parent categories with children MUST NOT have tool_calls. Only leaf categories can have tool_calls.
- Do NOT create an "other" subcategory — the system handles that automatically.
- Use the provided icons for top-level categories. For custom subcategories you add, use a GNOME symbolic icon name that fits.
"""

CLASSIFIER_BASE_PROMPT = """You classify the current desktop event into one allowed category path.

Rules:
- Return only one allowed path exactly, or `unclassified`.
- Classify by current intention, not just the app name.
- Prefer a child path when the signal is strong.
- Use `coding` for active software development and technical browser content that directly supports active development.
- Use `writing` for drafting or editing substantial text.
- Use `learning` for tutorials, study sessions, educational videos, or reading to understand.
- Use `communication` for email, chat, and meetings.
- Use `admin` for task managers, calendar, planning, finance, forms, and routine operations.
- Use `browsing` for general browsing, social media, shopping, news, casual reference, and non-goal-directed web use.
- Use `browsing/reference` only for generic lookup or reading that is not active development and not structured learning.
- Use `media` for passive entertainment through video or audio.
- Prefer a matching broad top-level category over `unclassified` when the current app or title clearly fits.
- Use `unclassified` only when no allowed path is plausible.
- Switch categories as soon as the user's intention changes. Do not keep the previous category just for stability.
- Do not explain your reasoning.
"""
