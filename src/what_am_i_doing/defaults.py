from __future__ import annotations

CLASSIFIER_BASE_PROMPT = """You classify the current GNOME desktop event into one activity and optionally one task.

Rules:
- Return JSON only.
- Always set `activity_path` to one allowed activity, `idle`, or `unknown`.
- Set `task_path` to an allowed task only when the current work clearly matches one.
- If no task matches, leave `task_path` null.
- For idle, choose `idle` and leave `task_path` null.
- Prefer a configured path over `unknown` when there is a plausible match.
- Switch activities or tasks as soon as the user's intention changes.
- Do not explain your reasoning.
"""
