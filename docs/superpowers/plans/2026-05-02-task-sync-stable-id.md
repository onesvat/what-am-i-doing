# Task Sync with Stable IDs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add task sync via configurable command and stable task IDs so span history survives task renames.

**Architecture:** `sync` section in config drives a periodic subprocess call. `CatalogEntry` gains required `id` field for tasks. `SpanRecord` uses `task_id` instead of `task_path`. Classifier stays unchanged — daemon resolves `task_path → task_id` after classification.

**Tech Stack:** Python 3.12, Pydantic, asyncio subprocess

---

### Task 1: Add `SyncConfig` and `id` field to models

**Files:**
- Modify: `src/waid/config.py`
- Modify: `src/waid/models.py`
- Modify: `config.example.yaml`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add `SyncConfig` to `config.py`**

Add after `ScreenshotConfig`:

```python
class SyncConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: list[str] = Field(default_factory=list)
    interval_minutes: int = 5
```

Add `sync: SyncConfig = Field(default_factory=SyncConfig)` to `AppConfig`.

- [ ] **Step 2: Add `id` field to `CatalogEntry` in models.py**

Add `id: str | None = None` to `CatalogEntry`. Activities leave `id` as None; tasks must have an `id`. Add a validator that enforces `id` uniqueness across tasks (not activities).

- [ ] **Step 3: Add `task_id` to `SpanRecord`**

Change `SpanRecord`:
```python
# Before
task_path: str | None = None

# After
task_id: str | None = None
```

- [ ] **Step 4: Add `task_id` to `PanelStateRecord` and `UIStateRecord`**

Add `task_id: str | None = None` to both models alongside the existing `task_path`. Update `PanelStateRecord.classified()` factory to accept `task_id`. Update `UIStateRecord.from_panel_state()` to carry `task_id`.

- [ ] **Step 5: Add `sync` section to config.example.yaml**

```yaml
sync:
  command: []  # e.g. ["python3", "sp-generate-tasks.py"]
  interval_minutes: 5
```

- [ ] **Step 6: Write tests**

Test that:
- `SyncConfig` with empty command means sync disabled
- `CatalogEntry` with `id` field parses correctly
- `SpanRecord` with `task_id` serializes correctly
- `PanelStateRecord.classified()` accepts `task_id`

- [ ] **Step 7: Run tests**

```bash
uv run python -m unittest discover -s tests -v
```

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "Add SyncConfig, task id, and task_id to models"
```

---

### Task 2: Update activity_catalog with id support

**Files:**
- Modify: `src/waid/activity_catalog.py`
- Modify: `tests/test_config.py` (or add a test for the catalog)

- [ ] **Step 1: Update `describe_tasks()` to include `id`**

In `SelectionCatalog.describe_tasks()`, include the `id` in the output:

```python
def describe_tasks(self) -> str:
    lines = []
    for entry in self.task_entries:
        id_part = f" (id={entry.id})" if entry.id else ""
        lines.append(f"- {entry.path}{id_part}: {entry.description or 'No description.'}")
    return "\n".join(lines)
```

- [ ] **Step 2: Add `task_path_to_id()` lookup to `SelectionCatalog`**

```python
def task_path_to_id(self, path: str) -> str | None:
    for entry in self.task_entries:
        if entry.path == path and entry.id:
            return entry.id
    return None
```

- [ ] **Step 3: Run tests and verify**

```bash
uv run python -m unittest discover -s tests -v
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "Add id to task descriptions and task_path_to_id lookup"
```

---

### Task 3: Update daemon to resolve task_id and add sync loop

**Files:**
- Modify: `src/waid/daemon.py`
- Modify: `src/waid/storage.py`
- Modify: `tests/test_daemon.py`

- [ ] **Step 1: Resolve `task_path → task_id` in span creation**

In `_close_previous_span()`, use `task_id` instead of `task_path` in `SpanRecord`. In `_publish_classified()`, resolve the task_id:

```python
task_id = self.runtime.catalog.task_path_to_id(result.task_path) if result.task_path else None
```

- [ ] **Step 2: Add `task_id` to panel state and UI state updates**

When building `PanelStateRecord`, pass `task_id` alongside `task_path`. Update `_build_ui_state()` to carry `task_id`.

- [ ] **Step 3: Add D-Bus property `PanelTaskId`**

In `dbus_service.py`, add a `PanelTaskId` property alongside `PanelTaskPath`.

- [ ] **Step 4: Add sync loop to daemon**

Add a `_sync_loop()` method that runs the configured sync command periodically:

```python
async def _sync_loop(self) -> None:
    if not self.config.sync.command:
        return
    while True:
        await asyncio.sleep(self.config.sync.interval_minutes * 60)
        try:
            process = await asyncio.create_subprocess_exec(
                *self.config.sync.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            result = await process.wait()
            if result == 0:
                await self.reload_config()
            else:
                self.debug.log("sync_failed", exit_code=result)
        except Exception as exc:
            self.debug.log("sync_error", error=str(exc))
```

Start it in `run()` and cancel on shutdown. Restart on config reload if interval changes.

- [ ] **Step 5: Write tests**

Test task_id resolution, sync loop start/stop, and panel state with task_id.

- [ ] **Step 6: Run tests**

```bash
uv run python -m unittest discover -s tests -v
```

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "Add task_id resolution and sync loop to daemon"
```

---

### Task 4: Update storage and tasks validation

**Files:**
- Modify: `src/waid/storage.py`
- Modify: `src/waid/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Update `load_tasks()` to validate `id` field**

In `load_tasks()`, after parsing entries, validate that task entries have `id` fields (if sync is enabled, `id` is required for tasks; if manual, `id` is optional). Raise a clear error on missing or duplicate IDs.

- [ ] **Step 2: Update `SpanRecord` serialization**

Ensure `task_id` (not `task_path`) is serialized correctly in span JSONL.

- [ ] **Step 3: Write tests for task validation**

- [ ] **Step 4: Run tests**

```bash
uv run python -m unittest discover -s tests -v
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "Add task id validation and update span serialization"
```

---

### Task 5: Update CLI stats display and task pinning

**Files:**
- Modify: `src/waid/__main__.py`
- Modify: `src/waid/daemon.py`

- [ ] **Step 1: Update stats display to resolve `task_id → task_path`**

In `_stats_payload()` and `_run_stats()`, resolve `task_id` back to `task_path` from the catalog for human display. If `task_id` is no longer in the catalog, display the raw `task_id`.

- [ ] **Step 2: Update task pinning to use `task_id`**

In `pin_focused_window_to_task()` and task pin storage, map `wm_class\x1ftitle → task_id` instead of `task_path`. On lookup, resolve `task_id → task_path` via catalog.

- [ ] **Step 3: Update `waid init` to prompt for sync command**

In the init wizard, add an optional prompt for `sync.command`.

- [ ] **Step 4: Run tests**

```bash
uv run python -m unittest discover -s tests -v
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "Update stats and pinning for task_id"
```

---

### Task 6: Update sp-generate-tasks.py

**Files:**
- Modify: `sp-generate-tasks.py`

- [ ] **Step 1: Add `id` field to output entries**

In `build_task_entries()`, include the SP task ID:

```python
entries.append({
    "id": task_id,
    "path": path,
    "description": ...,
    "icon": "folder-symbolic",
})
```

- [ ] **Step 2: Test manually**

```bash
uv run python sp-generate-tasks.py --help
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "Add id field to sp-generate-tasks.py output"
```

---

### Task 7: Update docs and config.example.yaml

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Document sync config in README**

Add a section about the `sync` config option and task IDs.

- [ ] **Step 2: Update AGENTS.md**

Add notes about `task_id` in `CatalogEntry`, `SpanRecord`, and the sync loop.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "Update docs for task sync and stable IDs"
```