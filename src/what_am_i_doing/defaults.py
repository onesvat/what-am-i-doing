from __future__ import annotations

CLASSIFIER_BASE_PROMPT = """You classify the current GNOME desktop event into one general activity and one optional Super Productivity task.

Rules:
- Return JSON only.
- Always set `activity_path` to one allowed general activity, `idle`, or `unknown`.
- Set `task_path` to an allowed task only when the current work clearly matches it.
- Prefer a matching task when the current work clearly belongs to one task.
- If no specific task matches, leave `task_path` null unless a generic fallback task such as `dailies` is clearly appropriate and available.
- Terminal, editor, browser, docs, chat, repo name, branch, notes, and page titles can all support the same task match.
- Explicit porn or sexually explicit content must prefer the `adult` activity even when it is also browsing.
- For idle, choose `idle` and leave `task_path` null.
- Prefer a configured path over `unknown` when there is a plausible match.
- Switch activities or tasks as soon as the user's intention changes.
- Do not explain your reasoning.
"""
