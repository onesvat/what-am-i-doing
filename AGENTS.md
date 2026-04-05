# AGENTS.md

This file describes how to work in this repository.

## Project Shape

`waid` is a GNOME-first desktop activity tracker.

Main pieces:

- Python daemon in [src/what_am_i_doing](/home/onur/.openclaw/workspace-coding/code/what-am-i-doing/src/what_am_i_doing)
- GNOME Shell extension in [extensions/gnome](/home/onur/.openclaw/workspace-coding/code/what-am-i-doing/extensions/gnome)
- Packaged runtime resources in [resources](/home/onur/.openclaw/workspace-coding/code/what-am-i-doing/src/what_am_i_doing/resources)
- Tests in [tests](/home/onur/.openclaw/workspace-coding/code/what-am-i-doing/tests)

User-facing product name:

- `waid`

Python package name:

- `what_am_i_doing`

Keep that split consistent. Do not rename the Python package casually.

## Product Rules

- GNOME-only is the current MVP.
- The user-facing CLI is `waid`.
- Config should stay small and user-friendly.
- Most low-level wiring should stay in code, not in YAML.
- Classifier must not run tools directly.
- Tool execution must stay bounded to configured action tools.
- `unknown` is the reserved fallback category.

If adding features, prefer simpler defaults over more config knobs.

## Code Style

- Use Python 3.12 features when they help clarity.
- Keep code straightforward and explicit.
- Prefer small functions with clear responsibilities.
- Avoid premature abstractions.
- Use ASCII unless a file already needs something else.
- Add comments only when the code would otherwise be hard to follow.

For shell commands in config:

- use argv arrays, not shell strings
- do not add shell parsing behavior to runtime execution

## Config Conventions

The current config format is versioned and intentionally minimal.

Important expectations:

- `model` is shared by generator and classifier
- `generator.categories` are broad user hints, not the final runtime taxonomy
- `tools.context` outputs are interpolated into `generator.instructions`
- `classifier.params` are interpolated into `classifier.instructions`
- `tools.actions` is the only action registry the generated taxonomy may reference

Do not reintroduce old top-level sections like provider, state_dir, extension toggles, or separate model blocks unless there is a strong reason.

## Runtime Conventions

- Prefer the running daemon over one-off local operations when a D-Bus control path exists.
- Keep raw event logging append-only.
- Keep taxonomy persistence resilient: last good taxonomy should survive generator failures.
- Validate generated taxonomy before using it.
- Only run actions on category changes.

## CLI Conventions

The CLI is part of the product, not a debug helper.

When adding commands:

- use `waid <noun> <verb>` or `waid <verb>` consistently
- keep output readable for humans by default
- add `--json` only where machine-readable output is useful
- avoid exposing internal implementation details in normal user flows

The expected first-time flow is:

1. `waid init`
2. `waid extension install`
3. `gnome-extensions enable waid@onesvat.github.io`
4. `waid service install --now`

Do not make this flow harder without a good reason.

## GNOME Extension Conventions

- Keep the extension focused on state capture and panel display.
- Do not move classification logic into the extension.
- Keep D-Bus names under the `org.waid.*` namespace.
- If changing D-Bus contracts, update both the Python daemon and the extension together.

## Testing

Before finishing changes, run relevant checks from the repo root.

Current baseline:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Useful extra checks:

```bash
.venv/bin/waid --help
.venv/bin/waid --config config.example.yaml config validate
.venv/bin/waid stats --json
```

If you change:

- config parsing: add or update config tests
- taxonomy or classification behavior: add or update taxonomy/classifier tests
- CLI/service behavior: add or update CLI/service tests
- GNOME integration: document manual verification steps in your final note

## Documentation

- Keep [README.md](/home/onur/.openclaw/workspace-coding/code/what-am-i-doing/README.md) user-friendly.
- README should explain setup, first run, config basics, and normal commands.
- Keep internal implementation detail in code or this file unless users actually need it.
- Update `config.example.yaml` when config behavior changes.

## Git

- Do not rewrite history unless explicitly asked.
- Do not revert unrelated user changes.
- Keep commits focused and readable.

Recommended commit style:

- short imperative summary
- example: `Add service install commands`
