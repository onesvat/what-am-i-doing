---
name: waid-train
description: Iterate on the waid classifier. Sample recent input→output pairs from debug.jsonl, spot misclassifications, propose and apply minimal prompt or catalog edits, restart the daemon, and truncate the debug log so the next cycle only reflects the new prompt. Use when the user says "train", "iterate", "tune classifier", or shares a misclassification complaint (e.g. "X şeklinde sınıflıyor ama yanlış").
---

# waid classifier training loop

Goal: tighten the waid classifier through small, auditable changes — without polluting future analysis with stale data.

## Inputs you rely on

- `~/.local/state/waid/debug.jsonl` — JSONL emitted by `DebugLogger` (only while `WAID_DEBUG=1` is set). Contains `classifier_attempt` (with full prompt) and `classifier_result` events.
- Source of truth for prompt/catalog:
  - `src/waid/defaults.py` — `CLASSIFIER_BASE_PROMPT`, the shared rules.
  - `src/waid/activity_catalog.py` — built-in activity paths and their descriptions.
  - `~/.config/waid/tasks.yaml` — task entries.

## Step 1 — Read

Use the helper to sample recent input→output pairs. Do **not** dump the full prompt — look only at state signals (title, wm_class, supporting windows) and the result JSON.

```
./skills/waid-train/sample_pairs.py --limit 40
```

Options:
- `--since <ISO>` — only pairs after timestamp (default: last service restart time, auto-detected).
- `--wm <pattern>` — filter by wm_class regex.
- `--only-misses` — skip results where activity_path is already what a human would likely pick (heuristic: trust idle/adult/media/system/gaming; flag everything else for review).

Read through the sample. Do not paste the whole prompt into the conversation — it is large and already audited.

## Step 2 — Learn

Group observations into patterns, not individual misses:

- "Terminal emulator wm_class + plain shell title → coding/ide" (recurring)
- "Browser with X keyword → generic browsing instead of task Y"
- "Editor/IDE wm_class returning unknown" (rare — might be noise)

Ignore one-off oddities unless they reveal a structural gap.

## Step 3 — Diagnose

Decide which knob to turn — cheapest first:

1. **Base prompt (`defaults.py`)** — when the rule is cross-cutting ("terminal emulators default to terminal"). Deterministic-leaning hints belong here.
2. **Activity description (`activity_catalog.py`)** — when two specific activities are being confused. Sharpen the boundary in both descriptions.
3. **Task description** — when the LLM doesn't match an obviously-relevant task. Edit `~/.config/waid/tasks.yaml` directly.

Keep edits minimal. No refactors.

## Step 4 — Apply

Make the edit. Show the diff or the specific lines to the user and wait for approval before restarting.

## Step 5 — Restart

```
systemctl --user restart waid.service
systemctl --user is-active waid.service
```

Confirm `active`.

## Step 6 — Truncate

Critical: the next iteration must only see data from the new prompt. Otherwise you'll keep pattern-matching on stale misclassifications.

```
truncate -s 0 ~/.local/state/waid/debug.jsonl
rm -f ~/.local/state/waid/debug.jsonl.1
```

Do **not** touch `activity.jsonl`, `spans.jsonl`, or `raw-events.jsonl` — those are user data.

## Step 7 — Hand off

Tell the user what changed, what to watch for, and how long to wait before the next iteration (usually: "a few hours of real use"). Do not start the next cycle automatically — training loops need human observation between rounds.

## Guardrails

- Never edit `defaults.py`/`activity_catalog.py` without showing the before/after.
- Never truncate the log before a successful restart — if restart fails, the old log is the only evidence of the regression.
- If you spot a bug in code (not a prompt issue), treat it as a normal bug fix, not a training step.
- Don't chase every miss. A 90% correct classifier is the goal, not 100%.
