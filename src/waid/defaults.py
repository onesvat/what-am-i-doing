from __future__ import annotations

CLASSIFIER_BASE_PROMPT = """Classify the current GNOME activity from window metadata and optional screenshot.

Rules:
- Output JSON only.
- Always set `activity_path` to a valid activity, `idle`, or `unknown`.
- Set `task_path` to a specific task when any title, app, URL, document, repo, or supporting window gives a plausible match; prefer a reasonable guess over `null`.
- Leave `task_path` null only for generic activities (idle, adult, media, social, shopping, news) or when no task-related evidence exists.
- For idle, use `activity_path: "idle"` and `task_path: null`.
- Prefer configured activity matches over `unknown` when plausible.
- Do not include explanations or reasoning in the output.

Screenshot guidance:
- Use visual content to confirm or enrich metadata (file types, repo names, branch, terminal cwd, visible URLs, document titles).
- If visual evidence contradicts metadata, trust the screenshot.
- If screenshot contains adult content, set `activity_path` to `adult`.
- If screenshot is unreadable, fall back to metadata.
"""
