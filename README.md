# waid

`waid` is a GNOME-first desktop activity tracker.

It watches the focused window, classifies the current work into one activity plus an optional task, shows the result in the GNOME panel, and can run your own action commands when the selection changes.

## How It Works

`waid` uses two sources of truth:

1. `~/.config/waid/config.yaml` for model settings, built-in activity filtering, custom activities, and action tools
2. `~/.config/waid/tasks.yaml` for generated or hand-written task entries

At runtime:

1. The GNOME extension reports the current desktop state.
2. The daemon loads `config.yaml` and `tasks.yaml`.
3. The classifier returns one `activity_path` and an optional `task_path`.
4. When either selection changes, `waid` records the span and runs any configured actions.

Built-in activities live in code. Users can allow or block them, and optionally add custom activities in `config.yaml`.

## Quick Start

### 1. Install

Using `uv`:

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e .
source .venv/bin/activate
```

Or with plain `pip`:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e .
source .venv/bin/activate
```

### 2. Create a Config

Run:

```bash
waid init
```

This writes `~/.config/waid/config.yaml`.

Then edit:

- `~/.config/waid/config.yaml`
- `~/.config/waid/tasks.yaml` if you want task-level matching

You can also start from [config.example.yaml](/home/onur/Code/what-am-i-doing/config.example.yaml).

### 3. Install the GNOME Extension

```bash
waid extension install
gnome-extensions enable waid@onesvat.github.io
```

If GNOME does not see the extension yet, log out and back in first.

### 4. Install the Service

```bash
waid service install --now
```

## Daily Commands

```bash
waid status
waid refresh
waid stats
waid service status
waid service logs
waid tracking pause
waid tracking resume
```

Useful helpers:

```bash
waid config path
waid config validate
waid extension status
```

`waid refresh` reloads both `config.yaml` and `tasks.yaml`.

## Config Shape

`config.yaml` stays intentionally small:

```yaml
version: 2

model:
  base_url: http://localhost:11434/v1
  name: gemma3:4b

classifier:
  retry_count: 2
  instructions: ""

allow_activities:
  - browsing/social_media
  - browsing/shopping
  - browsing/llm
  - browsing/research
  - browsing/news
  - browsing/other
  - coding/ide
  - coding/terminal
  - communication/chat
  - communication/email
  - communication/meetings
  - communication/other
  - admin
  - writing
  - learning
  - media/video
  - media/audio
  - media/other
  - system
  - gaming
  - adult

activities:
  - path: custom/research
    description: Reading and investigation outside the built-in activity catalog

tools:
  actions:
    example_tool:
      run: ["echo", "activity-changed"]
```

`tasks.yaml` is a plain YAML list:

```yaml
- path: dailies
  description: General work fallback when no more specific task matches
  icon: folder-symbolic

- path: fix-waid
  description: Terminal, editor, docs, and chats related to fixing waid
  icon: folder-symbolic
```

## GNOME Panel Behavior

The extension shows:

- the current activity and optional task
- every configured activity or task in today's list, even if its time is `0m`
- any extra paths that already appear in today's spans, even if they were later removed from config

The extension does not build its own menu model. It renders rows produced by the daemon.

## State Files

Inside `~/.local/state/waid/`:

- `raw-events.jsonl` records raw GNOME window events
- `activity.jsonl` records activity and task changes
- `status.json` stores the current UI payload used by the extension
- `spans.jsonl` stores closed spans for stats
- `tracking.json` stores paused/resumed state
- `debug.jsonl` stores debug events when `WAID_DEBUG=1`

## Notes

- `unknown` is the reserved fallback activity.
- `idle` is operational state, not a user-defined activity.
- Action commands must be argv arrays, not shell strings.
- Activity and task paths must be unique across the merged runtime catalog.
