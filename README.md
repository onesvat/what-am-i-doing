# waid

`waid` is a GNOME-first desktop activity tracker.

It watches the focused window, asks a classifier to pick one configured path such as `work/project-a` or `browsing/reference`, shows the current result in the GNOME panel, and can run your own action commands when the selection changes.

## How It Works

`waid` now has a simple runtime model:

1. The GNOME extension reports the current desktop state.
2. The daemon loads `config.yaml` plus any imported choice files.
3. The classifier chooses one allowed path or `unknown`.
4. When the chosen path changes, `waid` records the span and runs any configured actions.

There is no generator loop and no runtime taxonomy file anymore. Your config is the source of truth.

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

This writes:

```text
~/.config/waid/config.yaml
```

`waid init` only asks for model connection details. Then edit the file and add your `choices`.

If you want to start from a file instead, copy [config.example.yaml](/home/onur/Code/what-am-i-doing/config.example.yaml).

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

These are the main commands:

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

`waid refresh` reloads `config.yaml` and any imported choice files. Use it after changing your config or regenerating an import file.

## Config Shape

The config is intentionally flat and small.

```yaml
version: 2

model:
  base_url: http://localhost:11434/v1
  name: gemma3:4b
  api_key_env: OPENAI_API_KEY
  timeout_seconds: 30
  temperature: 0.0

classifier:
  retry_count: 2
  instructions: |
    Prefer work/project-a for that repo.
    Use browsing/reference for generic reading.
    Return unknown when nothing fits.

choices:
  - path: work/project-a
    description: Main project work
    icon: laptop-symbolic
    actions:
      - tool: sp_start
        args: ["123"]
  - path: browsing/reference
    description: Reading and lookup
    icon: text-x-generic-symbolic
  - import: ~/.config/waid/choices.yaml

tools:
  actions:
    sp_start:
      run: ["sp", "task", "start"]

idle_threshold_seconds: 60
classify_idle: true
```

## Choice Imports

Imports are plain YAML files that contain the same flat list shape used under `choices`.

Example:

```yaml
- path: work/project-b
  description: Another active project
  icon: laptop-symbolic
- path: admin/inbox
  description: Inbox cleanup and planning
```

`waid` does not run scripts to produce this file. If you want dynamic choices, generate the YAML yourself with your own script, then run `waid refresh`.

## GNOME Panel Behavior

The extension shows:

- the current selected path
- every configured choice from the current config, even if its time is `0m`
- any extra paths that already appear in today's spans, even if they were removed from the config later

The extension does not build its own menu model. It renders the rows produced by the daemon.

## State Files

Inside `~/.local/state/waid/`:

- `raw-events.jsonl` records raw GNOME window events
- `activity.jsonl` records selection changes
- `status.json` stores the current UI payload used by the extension
- `spans.jsonl` stores closed activity spans for stats
- `tracking.json` stores paused/resumed state
- `debug.jsonl` stores debug events when `WAID_DEBUG=1`

## Notes

- `unknown` is the reserved fallback returned by the classifier when no configured path fits.
- `idle` is operational state, not a user-defined choice.
- Action commands must be argv arrays, not shell strings.
- Choice paths must be unique.
