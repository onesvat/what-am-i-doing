# waid

`waid` watches your GNOME desktop, decides what kind of work you are doing, and runs your own commands when that activity changes.

Examples:

- switch a Super Productivity task when you move into a project
- update Home Assistant with `coding`, `messaging`, or `surfing`
- alert yourself when browsing matches a category you want to avoid
- show the current top-level status in the GNOME panel

The goal is simple: install it once, keep the config small, and manage it like a normal desktop service.

## What Changed

This project now uses a simpler product shape:

- the command is `waid`
- config lives at `~/.config/waid/config.yaml`
- state lives at `~/.local/state/waid/`
- GNOME extension id is `waid@gnome`
- service name is `waid.service`

Most low-level settings are not exposed in the main config anymore.

## How It Works

`waid` has three moving parts:

1. The GNOME extension tells `waid` which window is focused.
2. A generator model builds a runtime category tree from your broad categories and your context commands.
3. A classifier model picks the best category path for each window change.

When the selected category changes, `waid` runs the predeclared action commands attached to that category.

The classifier does not run tools. It only chooses from the generated category list.

## Install

### 1. Create an environment

Using `uv`:

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e .
```

Or with plain `pip`:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e .
```

### 2. Create your config

Run:

```bash
waid init
```

The init wizard asks for:

- model base URL
- model name
- API key env var name
- broad categories
- optional notes for those categories
- context commands
- action commands
- short extra instructions

When it finishes, it writes:

```text
~/.config/waid/config.yaml
```

If you prefer manual editing, copy [config.example.yaml](/home/onur/.openclaw/workspace-coding/code/what-am-i-doing/config.example.yaml).

### 3. Install the GNOME extension

```bash
waid extension install
gnome-extensions enable waid@gnome
```

If the panel item does not appear, restart GNOME Shell or log out and back in.

### 4. Install and start the user service

```bash
waid service install --now
```

Useful service commands:

```bash
waid service status
waid service restart
waid service stop
waid service logs
```

## Everyday Commands

```bash
waid status
waid refresh
waid stats
waid doctor
waid config validate
waid extension status
```

## The Config Format

The config is intentionally small.

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
    Use unknown when unclear.
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
- `name`: model id at that endpoint
- `api_key_env`: environment variable to read the API key from
- `timeout_seconds`: HTTP timeout
- `temperature`: model temperature

### `generator`

This controls the slower refresh loop that builds the runtime taxonomy.

- `interval_minutes`: how often context commands are refreshed
- `retry_count`: retries before keeping the last good taxonomy
- `categories`: broad names you care about
- `instructions`: extra prompt text for generation

`unknown` is added automatically. You do not need to define it.

### `classifier`

This controls the fast per-window decision loop.

- `retry_count`: how many times to retry invalid category output
- `instructions`: extra prompt text for classification
- `params`: simple variables for `${name}` substitution inside `instructions`

### `tools.context`

These commands run on the generator refresh interval. Their output becomes prompt text for generation.

If a context tool is named `sp_today_tasks`, you can use it inside generator instructions as:

```text
${sp_today_tasks}
```

### `tools.actions`

These are the only commands the generated taxonomy is allowed to call.

They are referenced by name from the generated category JSON.

Example:

- action tool name: `sp_switch`
- configured command: `["sp", "switch"]`
- generated call: `{"tool":"sp_switch","args":["123"]}`

That becomes:

```bash
sp switch 123
```

## Conventions

These conventions matter because the models depend on them.

- Tool names should look like identifiers: `sp_switch`, `ha`, `telegram`
- Context tool names are also variable names inside generator instructions
- Commands are argv arrays, not shell strings
- Category names cannot contain `/`
- Top-level categories should stay broad
- Child categories are generated at runtime and should be specific enough to trigger useful actions

## Common Use Cases

### Super Productivity

Context tool:

```yaml
tools:
  context:
    sp_today_tasks:
      run: ["sp", "list", "today"]
```

Action tool:

```yaml
tools:
  actions:
    sp_switch:
      run: ["sp", "switch"]
```

Generator instruction:

```text
Today's tasks:
${sp_today_tasks}

When useful, create child categories that map clearly to those tasks.
```

Expected result:

- generator creates child categories for today’s work
- classifier picks one of them on focus changes
- `waid` runs `sp switch <task_id>` when the path changes

### Home Assistant status

Action tool:

```yaml
tools:
  actions:
    ha:
      run: ["ha"]
```

The generator can attach calls like:

```json
{"tool":"ha","args":["coding"]}
```

So when the selected category becomes `coding`, `waid` runs:

```bash
ha coding
```

### Telegram notifications

Action tool:

```yaml
tools:
  actions:
    telegram:
      run: ["telegram-send"]
```

You can attach Telegram notifications to any generated category path you care about. For example, you might notify yourself when `waid` switches into a distraction-related browsing category or when a planning session starts.

## Files Written By waid

Under `~/.local/state/waid/`:

- `raw-events.jsonl`: every raw GNOME state change
- `activity.jsonl`: interpreted category changes
- `taxonomy.json`: last good generated taxonomy
- `status.json`: current category path
- `spans.jsonl`: duration spans for stats

## Troubleshooting

### `waid status` shows `source: state-file`

The daemon D-Bus service is not reachable. Check:

```bash
waid service status
waid service logs
```

### The extension is installed but the panel item does not update

Check:

```bash
waid extension status
waid doctor
```

Then restart GNOME Shell or log out and back in.

### A tool command never runs

Check:

- the tool binary exists in `PATH`
- the tool name in generated taxonomy matches a configured `tools.actions` entry
- the command works manually in your user session

### The model keeps returning invalid categories

Make classifier instructions shorter and stricter. The classifier only needs to return one allowed path exactly.

## Current Limits

- GNOME only
- one shared model block for generator and classifier
- classifier runs no tools
- the init wizard is interactive and terminal-based
- extension install is handled by CLI, but enabling the extension is still a separate GNOME command

## Developer Notes

The package still uses the Python module name `what_am_i_doing`, but the user-facing product name and CLI are `waid`.
