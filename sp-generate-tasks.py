#!/usr/bin/env python3
"""Generate ~/.config/waid/tasks.yaml from today's Super Productivity tasks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.config import default_config_path, default_tasks_path, load_config
from what_am_i_doing.llm import OpenAICompatibleClient

import yaml


TURKISH_CHAR_MAP = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "Ç": "c",
        "Ğ": "g",
        "İ": "i",
        "Ö": "o",
        "Ş": "s",
        "Ü": "u",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate waid tasks.yaml from SP tasks.")
    parser.add_argument("--config", default=str(default_config_path()))
    parser.add_argument("--output", default=str(default_tasks_path()))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    output_path = Path(args.output).expanduser()
    sp_binary = detect_sp_binary(config)
    try:
        tasks = load_sp_tasks(sp_binary)
        generated = build_task_entries(tasks, config=config)
        content = yaml.safe_dump(generated, sort_keys=False, allow_unicode=True)
        changed = write_if_changed(output_path, content)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    status = "updated" if changed else "unchanged"
    print(f"{status}: {output_path} ({len(generated)} tasks)")
    return 0


def detect_sp_binary(config) -> str:
    try:
        return config.tools.actions["sp_start"].run[0]
    except Exception:
        return "sp"


def load_sp_tasks(sp_binary: str) -> list[dict]:
    result = subprocess.run(
        [sp_binary, "task", "list", "--today", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "sp task list failed")
    payload = json.loads(result.stdout)
    if not isinstance(payload, list):
        raise ValueError("expected Super Productivity task list JSON array")
    return [task for task in payload if isinstance(task, dict)]


def build_task_entries(tasks: list[dict], *, config) -> list[dict]:
    llm = OpenAICompatibleClient()
    used_paths: set[str] = set()
    entries: list[dict] = []
    for task in tasks:
        task_id = str(task.get("id", "")).strip()
        title = str(task.get("title", "")).strip()
        if not task_id or not title or bool(task.get("isDone")):
            continue
        path = uniquify_path(slugify(title), task_id, used_paths)
        entries.append(
            {
                "path": path,
                "description": describe_task(task, config=config, llm=llm),
                "icon": "folder-symbolic",
                "actions": [{"tool": "sp_start", "args": [task_id]}],
            }
        )
    return entries


def describe_task(task: dict, *, config, llm: OpenAICompatibleClient) -> str:
    title = str(task.get("title", "")).strip()
    project = str(task.get("project", "") or task.get("projectId", "")).strip()
    notes = str(task.get("notes", "")).strip()
    prompt = [
        "Write one short description for a desktop activity classifier.",
        "Focus on likely actions, pages, chats, commands, repositories, or documents that indicate this task is active.",
        "Do not mention Super Productivity, IDs, or formatting instructions.",
        f"Task title: {title}",
    ]
    if project:
        prompt.append(f"Project: {project}")
    if notes:
        prompt.append(f"Notes: {notes}")
    response = llm.chat(
        config.classifier_model,
        [{"role": "user", "content": "\n".join(prompt)}],
        max_tokens=120,
    )
    return response.strip().replace("\n", " ")


def slugify(value: str) -> str:
    lowered = value.strip().translate(TURKISH_CHAR_MAP).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "task"


def uniquify_path(base_path: str, task_id: str, used_paths: set[str]) -> str:
    candidate = base_path
    if candidate in used_paths:
        candidate = f"{base_path}-{task_id}"
    suffix = 2
    while candidate in used_paths:
        candidate = f"{base_path}-{task_id}-{suffix}"
        suffix += 1
    used_paths.add(candidate)
    return candidate


def write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    if previous == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
