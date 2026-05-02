# Task Sync with Stable IDs

**Date:** 2026-05-02  
**Status:** Approved  

## Problem

Activity tracking works, but task tracking relies on manually maintained `tasks.yaml`. Users who manage tasks in external tools (e.g., Super Productivity) must run separate scripts (`sp-generate-tasks.py`, `sp-task-monitor.py`) via cron, creating setup friction and confusion. Additionally, task paths in spans are unstable — if a task is renamed, historical spans lose their link to the task.

## Goals

1. Make task syncing a first-class config option in waid — no external cron needed.
2. Introduce stable task IDs so span history survives task renames and removals.
3. Keep SP (or any external tool) optional — manual `tasks.yaml` still works.
4. Don't break the classifier's `task_path` flow; resolve to `task_id` only at span/storage time.

## Design

### 1. Config: `sync` section

A new top-level `sync` section in `config.yaml`:

```yaml
sync:
  command: ["python3", "sp-generate-tasks.py"]  # argv array
  interval_minutes: 5
```

- If `sync` is absent or `command` is empty/missing — sync is disabled; manual `tasks.yaml` is the only source.
- `command` is an argv array (same pattern as `tools.actions`), not a shell string.
- `interval_minutes` defaults to 5 if `sync` is present but omitted.
- The daemon runs the command via `asyncio.create_subprocess_exec` on a periodic timer.
- On success: daemon silently reloads the catalog (no classification pause).
- On failure: error is logged, old tasks remain in effect.
- Config reload (`waid refresh` or D-Bus `ReloadConfig`) restarts the sync timer if interval changes.

### 2. Task model: `id` field on `CatalogEntry`

`CatalogEntry` gains a required `id` field:

```yaml
# Synced from SP
- id: "12345"
  path: my-project/refactor-auth
  description: "Refactoring the authentication module"
  icon: folder-symbolic

# Manual entry
- id: "manual-weekly-review"
  path: admin/weekly-review
  description: "Weekly review and planning"
  icon: folder-symbolic
```

Validation rules:
- `id` is required for all task entries.
- `id` must be unique across the entire catalog (activities + tasks).
- `id` cannot collide with reserved names (`unknown`, `idle`, `classified`, etc.).
- Activity entries (built-in or custom) do not have an `id` field — only tasks do.

### 3. Span model: `task_id` replaces `task_path`

`SpanRecord` changes:

```python
# Before
task_path: str | None = None

# After
task_id: str | None = None
```

- When the classifier returns a `task_path`, the daemon resolves it to `task_id` via the catalog lookup (`task_path → CatalogEntry.id`).
- If resolution fails (task removed between classification and span creation), `task_id` is set to `None`.
- Old span files with `task_path` are incompatible; no migration is needed (user confirmed backward compatibility is not a concern).

### 4. Panel state: `task_id` added alongside `task_path`

`PanelStateRecord` and `UIStateRecord` keep `task_path` (for human-readable display) and gain `task_id` (for programmatic use):

```python
task_path: str | None = None   # kept for display
task_id: str | None = None      # added for stability
```

D-Bus properties gain `PanelTaskId` alongside existing `PanelTaskPath`.

### 5. Classifier: no changes

The classifier still works with `task_path` values. Its prompt still lists allowed `task_path` values and their descriptions. The classifier returns `ClassificationResult(task_path=...)` as before.

The daemon resolves `task_path → task_id` when creating spans or updating panel state. The classifier is unaware of IDs.

### 6. Stats display: resolve `task_id` to current path

When displaying stats:
- Resolve `task_id` to current path from the catalog.
- If `task_id` is no longer in the catalog, display the raw `task_id` (e.g., `12345`).
- Activity paths in spans are unaffected — they use the same `path` field as before.

### 7. Daemon changes: sync loop

The `ActivityDaemon` starts an `asyncio.Task` running a sync loop:

```
_sync_loop():
    while running:
        await asyncio.sleep(interval * 60)
        try:
            result = await asyncio.create_subprocess_exec(*command)
            if result.returncode == 0:
                await self._reload_config()
            else:
                log.warning("sync command failed with exit code %d", result.returncode)
        except Exception:
            log.exception("sync command error")
```

- The sync loop runs in the background; classification continues during sync.
- `_reload_config()` re-reads `config.yaml` and `tasks.yaml`, rebuilds the catalog, and reconciles panel state with the new catalog.
- If the sync command takes longer than `interval_minutes`, the next cycle is delayed (no overlap).

### 8. Sync script contract

The configured script:
- Writes to `~/.waid/tasks.yaml` (standard path).
- Must include the `id` field in every entry.
- Exit code 0 = success; non-zero = failure.
- stdout/stderr are logged at debug level.
- The daemon does not parse script output; it only checks exit code and then reloads.

### 9. `sp-generate-tasks.py` updates

The existing script is updated:
- Output format includes `id` field using SP's task ID (e.g., `id: "12345"`).
- All other behavior is preserved (LLM description generation, slug creation, etc.).
- The script remains a standalone script; it is not imported by the daemon.

### 10. What stays the same

- Manual `tasks.yaml` workflow: users who don't use sync can still write tasks by hand, they just need to add `id` fields.
- Activity catalog: built-in activities and custom activities don't have IDs and don't need them.
- Classifier prompt: no changes to the prompt structure or classification logic.
- Task pinning: `task-pins.json` maps `wm_class\x1ftitle → task_id` (was `task_path`, now `task_id`). Pinning operations accept `task_id` instead of `task_path`.
- `waid init`: should prompt for optional sync command during setup.

## Data flow summary

```
SP (or any tool)
  │
  ▼ (script writes tasks.yaml with id field)
tasks.yaml
  │
  ▼ (daemon reads on startup + after sync)
ActivityCatalog
  │
  ├── Classifier uses task_path + description (unchanged)
  ├── Daemon resolves task_path → task_id for spans and panel state
  └── Stats resolves task_id → task_path for display
```

## Files to change

| File | Change |
|------|--------|
| `src/waid/models.py` | Add `id` to `CatalogEntry`; change `task_path` to `task_id` in `SpanRecord`; add `task_id` to `PanelStateRecord`/`UIStateRecord` |
| `src/waid/config.py` | Add `SyncConfig` model; load/validate `sync` section; validate task `id` uniqueness |
| `src/waid/activity_catalog.py` | Update `describe_tasks()` to include `id` in output for resolution; add `task_path_to_id()` lookup |
| `src/waid/daemon.py` | Add sync loop; resolve `task_path → task_id` in span creation and panel state updates; update `_reload_config` to restart sync timer |
| `src/waid/defaults.py` | No changes needed |
| `src/waid/classifier.py` | No changes needed |
| `src/waid/storage.py` | `load_tasks()` validates `id` field; `SpanRecord` field name change |
| `src/waid/__main__.py` | Stats display resolves `task_id → task_path`; update `PinFocusedWindowToTask` D-Bus method |
| `sp-generate-tasks.py` | Add `id` field to output entries |
| `config.example.yaml` | Add `sync` section with examples |
| `tests/` | Update all tests for new `id` field and `task_id` in models |