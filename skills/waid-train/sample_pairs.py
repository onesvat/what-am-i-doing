#!/usr/bin/env python3
"""Sample recent classifier input -> output pairs from debug.jsonl.

Prints only the decision-relevant signals (title, wm_class, supporting windows)
and the LLM result. Does not dump the full prompt.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

DEBUG_LOG = Path.home() / ".local/state/waid/debug.jsonl"

GENERIC_OK = {"idle", "adult", "system", "gaming", "media/video", "media/audio", "media/other"}


def parse_attempt(entry: dict) -> dict:
    prompt = entry.get("prompt", "")
    title = wm = ws = ""
    supporting: list[str] = []
    in_supp = False
    for line in prompt.split("\n"):
        if line.startswith("title: "):
            title = line[7:]
        elif line.startswith("wm_class: "):
            wm = line[10:]
        elif line.startswith("workspace_name: "):
            ws = line[16:]
        elif line.startswith("Supporting open windows:"):
            in_supp = True
        elif in_supp and line.startswith("- "):
            supporting.append(line[2:])
        elif in_supp and not line.strip():
            in_supp = False
    return {"title": title, "wm": wm, "ws": ws, "supp": supporting}


def load_pairs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    pairs: list[dict] = []
    for i, line in enumerate(lines):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("event") != "classifier_attempt":
            continue
        state = parse_attempt(d)
        for j in range(i + 1, min(i + 6, len(lines))):
            try:
                r = json.loads(lines[j])
            except json.JSONDecodeError:
                continue
            if r.get("event") == "classifier_result":
                pairs.append(
                    {
                        "ts": d.get("ts", ""),
                        "attempt": d.get("attempt", 0),
                        "result": r.get("result", ""),
                        **state,
                    }
                )
                break
    return pairs


def detect_last_restart() -> str | None:
    try:
        out = subprocess.run(
            [
                "systemctl",
                "--user",
                "show",
                "waid.service",
                "--property=ActiveEnterTimestamp",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    for line in out.stdout.splitlines():
        if line.startswith("ActiveEnterTimestamp="):
            value = line.split("=", 1)[1].strip()
            if not value or value == "0":
                return None
            try:
                import datetime as _dt

                stamp = _dt.datetime.strptime(value, "%a %Y-%m-%d %H:%M:%S %Z")
                return stamp.astimezone(_dt.timezone.utc).isoformat()
            except ValueError:
                return None
    return None


def parse_result(raw: str) -> tuple[str, str | None] | None:
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    ap = obj.get("activity_path")
    tp = obj.get("task_path")
    if not isinstance(ap, str):
        return None
    return ap, tp if isinstance(tp, str) else None


def looks_generic(activity: str) -> bool:
    return activity in GENERIC_OK or activity.startswith("browsing/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--since", default=None, help="ISO timestamp; default = last service restart")
    parser.add_argument("--wm", default=None, help="regex on wm_class")
    parser.add_argument("--only-misses", action="store_true")
    parser.add_argument("--path", default=str(DEBUG_LOG))
    args = parser.parse_args()

    since = args.since or detect_last_restart()
    pairs = load_pairs(Path(args.path).expanduser())
    if since:
        pairs = [p for p in pairs if p["ts"] >= since]
    if args.wm:
        rx = re.compile(args.wm)
        pairs = [p for p in pairs if rx.search(p["wm"])]
    if args.only_misses:
        filtered = []
        for p in pairs:
            parsed = parse_result(p["result"])
            if parsed is None:
                filtered.append(p)
                continue
            ap, _ = parsed
            if not looks_generic(ap):
                filtered.append(p)
        pairs = filtered

    total = len(pairs)
    if args.limit > 0:
        pairs = pairs[-args.limit :]

    print(f"# since={since or 'all'} showing={len(pairs)}/{total}")
    for p in pairs:
        ts = p["ts"][11:19]
        print(f"[{ts}] {p['wm']} ws={p['ws']}")
        print(f"  title: {p['title'][:140]}")
        for s in p["supp"][:2]:
            print(f"  supp:  {s[:140]}")
        print(f"  -> {p['result']}")


if __name__ == "__main__":
    main()
