# waid

`waid` helps your GNOME desktop understand what you are doing right now.

It watches your active window, picks a category like `coding` or `planning`, and can run your own commands when that category changes.

## Why Use It? 🙂

With `waid`, you can:

- switch your current Super Productivity task automatically
- update Home Assistant with your current work mode
- show your current status in the GNOME top bar
- keep lightweight logs of what you worked on during the day
- build your own automations without hardcoding rules in Python

## How It Works

`waid` has three simple pieces:

1. 🖥️ A GNOME extension tells `waid` which window is focused.
2. 🧠 A generator model builds a small category tree from your config and context commands.
3. ⚡ A classifier model picks the best category for each window change.

When the category changes, `waid` runs the action commands attached to that category.

## Quick Start

### 1. Install it

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

If you do not want to activate the environment, use the binary directly:

```bash
.venv/bin/waid init
```

### 2. Create your config

Run:

```bash
waid init
```

If you skipped activation, run:

```bash
.venv/bin/waid init
```

The setup wizard will ask for:

- your LLM endpoint
- your model name
- broad categories you care about
- context commands like `sp list today`
- action commands like `sp switch` or `ha`
- short extra instructions

Your config will be written to:

```text
~/.config/waid/config.yaml
```

If you want to start from a file instead, copy [config.example.yaml](/home/onur/.openclaw/workspace-coding/code/what-am-i-doing/config.example.yaml).

### 3. Install the GNOME extension

Right now the extension is targeted at GNOME 49.

```bash
waid extension install
gnome-extensions enable waid@onesvat.github.io
```

If `gnome-extensions enable waid@onesvat.github.io` says the extension does not exist yet, log out and back in first, then run the command again.

If you do not see the top bar item after enabling, restart GNOME Shell or log out and back in.

### 4. Install the service

```bash
waid service install --now
```

That makes `waid` run as a user service in the background.

## Daily Commands

These are the commands you will actually use most of the time:

```bash
waid status
waid refresh
waid stats
waid doctor
waid service status
waid service logs
```

Useful config helpers:

```bash
waid config path
waid config validate
waid extension status
```

### Debug Mode

If you want to debug what `waid` receives and what it sends to the model, start it with:

```bash
WAID_DEBUG=1 waid run
```

Or for the service:

```bash
systemctl --user edit waid.service
```

Add:

```ini
[Service]
Environment=WAID_DEBUG=1
```

Then reload and restart:

```bash
systemctl --user daemon-reload
systemctl --user restart waid.service
```

Debug entries are written to:

```text
~/.local/state/waid/debug.jsonl
```

This includes provider state, rendered prompts, raw LLM responses, classifier results, and tool execution output.

For a human-readable view, use:

```bash
waid debug logs
```

Follow live debug output:

```bash
waid debug logs --follow
```

If you still want the raw JSON lines:

```bash
waid debug logs --json
```

## The Config, Explained Simply

The config is small on purpose.

```yaml
version: 1

model:
  base_url: http://localhost:11434/v1
  name: gemma3:4b
  api_key_env: OPENAI_API_KEY
  timeout_seconds: 30
  temperature: 0.0

generator:
  interval_minutes: 5
  retry_count: 1
  categories:
    - name: coding
    - name: messaging
      note: email, chat, meetings
    - name: planning
    - name: surfing
  instructions: |
    Prefer matching today's planned tasks when possible.
    Today's tasks:
    ${sp_today_tasks}

classifier:
  retry_count: 2
  instructions: |
    Prefer the most specific category.
    Use unclassified when no category fits.
  params:
    work_mode: focused

tools:
  context:
    sp_today_tasks:
      run: ["sp", "list", "today"]
      timeout_seconds: 10
  actions:
    sp_switch:
      run: ["sp", "switch"]
      timeout_seconds: 10
    ha:
      run: ["ha"]
      timeout_seconds: 10
    telegram:
      run: ["telegram-send"]
      timeout_seconds: 10
```

### `model`

This is the shared model config for both generator and classifier.

- `base_url`: your OpenAI-compatible endpoint
- `name`: model id
- `api_key_env`: env var used for the API key
- `timeout_seconds`: request timeout
- `temperature`: model temperature

### `generator`

This is the slower loop.

It:

- reads your broad categories
- runs context commands
- builds a runtime category tree

### `classifier`

This is the fast loop that runs on window changes.

It:

- receives the current desktop event
- sees the generated category list
- returns one allowed category path

It does not run tools directly.

### `tools.context`

These commands give extra daily context to the generator.

Example:

```yaml
tools:
  context:
    sp_today_tasks:
      run: ["sp", "list", "today"]
```

Then you can use the output inside `generator.instructions` like this:

```text
${sp_today_tasks}
```

### `tools.actions`

These are the only commands `waid` is allowed to execute as actions.

Example:

```yaml
tools:
  actions:
    sp_switch:
      run: ["sp", "switch"]
```

If the generated taxonomy returns:

```json
{"tool":"sp_switch","args":["123"]}
```

`waid` will run:

```bash
sp switch 123
```

## Common Setups

### ✅ Super Productivity

Use a context tool for today's tasks:

```yaml
tools:
  context:
    sp_today_tasks:
      run: ["sp", "list", "today"]
```

Use an action tool for switching:

```yaml
tools:
  actions:
    sp_switch:
      run: ["sp", "switch"]
```

Then guide the generator with something like:

```text
Today's tasks:
${sp_today_tasks}

Create useful child categories when they clearly match these tasks.
```

### ✅ Home Assistant

```yaml
tools:
  actions:
    ha:
      run: ["ha"]
```

Then generated categories can trigger:

```json
{"tool":"ha","args":["coding"]}
```

Which becomes:

```bash
ha coding
```

### ✅ Telegram Notifications

```yaml
tools:
  actions:
    telegram:
      run: ["telegram-send"]
```

You can attach Telegram notifications to any generated category you want.

Examples:

- notify when you enter a distraction-related browsing category
- notify when a planning session starts
- notify when a work session moves into a specific project

## Files `waid` Writes

Inside `~/.local/state/waid/`:

- `raw-events.jsonl` → every raw GNOME event
- `activity.jsonl` → category changes
- `taxonomy.json` → last good generated taxonomy
- `status.json` → current selected path
- `spans.jsonl` → duration spans used by stats

## Conventions

These are worth knowing:

- tool names should look like `sp_switch` or `ha`
- commands must be argv arrays, not shell strings
- category names cannot contain `/`
- top-level categories should stay broad
- child categories should be useful enough to trigger real actions

## Troubleshooting

### `waid status` says `source: state-file`

That usually means the daemon is not reachable over D-Bus.

Check:

```bash
waid service status
waid service logs
```

### The GNOME top bar item is missing

Check:

```bash
waid extension status
waid doctor
```

Then restart GNOME Shell or log out and back in.

### GNOME says the extension is `OUT OF DATE`

This usually means GNOME Shell has not reloaded the extension metadata yet.

After `waid extension install`, log out and back in, then run:

```bash
gnome-extensions enable waid@onesvat.github.io
```

### A command never runs

Check:

- the command exists in `PATH`
- the tool name used by the taxonomy exists in `tools.actions`
- the command works manually in your terminal

### The model keeps choosing invalid categories

Make the classifier instructions shorter and stricter.

Good rule:

- return only one path
- use `unclassified` only when no category fits

## Current Limits

- GNOME only
- one shared model block for generator and classifier
- classifier does not run tools
- extension install is handled by CLI, but GNOME enabling is still a separate command

## Developer Note

The user-facing product is called `waid`, but the Python package name is still `what_am_i_doing`.
