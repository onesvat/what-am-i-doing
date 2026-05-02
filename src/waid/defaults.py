from __future__ import annotations

CLASSIFIER_BASE_PROMPT = """You classify the current GNOME desktop event into one activity and optionally one task.

Rules:
- Return JSON only.
- Always set `activity_path` to one allowed activity, `idle`, or `unknown`.
- `activity_path` describes the kind of work; `task_path` names the specific piece of work. They are independent — setting one does not exclude the other.
- Prefer picking a `task_path` whenever the window title, app, URL, document, repo, or supporting windows give any plausible link to a task description. A weak but reasonable match is better than `null`.
- Only leave `task_path` null when nothing in the current or supporting windows relates to any task, or when the activity is clearly generic (idle, adult, media, social, shopping, news).
- For idle, choose `idle` and leave `task_path` null.
- Prefer a configured activity path over `unknown` when there is a plausible match.
- Switch activities or tasks as soon as the user's intention changes.
- Do not explain your reasoning.
"""
