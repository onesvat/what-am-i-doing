# Visual Classification + Unified State Dir Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add visual classification via screenshots and complete the state directory consolidation to `~/.waid/`.

**Architecture:** Extension captures screenshots → saves to `~/.waid/screenshots/` → sends path via D-Bus → daemon passes to classifier → classifier uses vision model when available → daemon cleans up old screenshots. State dir consolidation is partially done (constants, storage migration, __main__ are updated); remaining work is extension JS paths and tests.

**Tech Stack:** Python 3.12, Pydantic, GNOME Shell Screenshot API, OpenAI Vision API format

---

### Task 1: Complete state dir consolidation (remaining pieces)

The following are already done: `constants.py` (WAID_DIR, SCREENSHOTS_DIR, LEGACY_*), `storage.py` (migrate_legacy_dirs), `__main__.py` (SCREENSHOTS_DIR mkdir, migrate_legacy_dirs call).

Remaining: update extension JS path constants, update tests.

**Files:**
- Modify: `extensions/gnome/extension.js`
- Modify: `src/waid/resources/gnome/extension.js`
- Modify: `tests/test_service.py`
- Modify: `tests/test_cli_main.py`
- Modify: `README.md`

- [ ] **Step 1: Update extension.js path constants (both copies)**

In both `extensions/gnome/extension.js` and `src/waid/resources/gnome/extension.js`, change:

```javascript
const STATE_DIR = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'state', 'waid']);
const STATUS_FILE = GLib.build_filenamev([STATE_DIR, 'status.json']);
const CONFIG_FILE = GLib.build_filenamev([GLib.get_home_dir(), '.config', 'waid', 'config.yaml']);
```

to:

```javascript
const WAID_DIR = GLib.build_filenamev([GLib.get_home_dir(), '.waid']);
const STATE_DIR = GLib.build_filenamev([WAID_DIR, 'state']);
const STATUS_FILE = GLib.build_filenamev([STATE_DIR, 'status.json']);
const CONFIG_FILE = GLib.build_filenamev([WAID_DIR, 'config.yaml']);
```

- [ ] **Step 2: Update tests for path changes**

In `tests/test_service.py`, check if any test assertions reference old paths (`-m what_am_i_doing` → already updated to `-m waid`). Check for any path assertions referencing `~/.config/waid` or `~/.local/state/waid`.

In `tests/test_cli_main.py`, check for any path assertions referencing old config/state directories.

- [ ] **Step 3: Update README.md**

Change all references from `~/.config/waid/` and `~/.local/state/waid/` to `~/.waid/`. Update the "State Files" section:

```markdown
Inside `~/.waid/`:

- `state/raw-events.jsonl` records raw GNOME window events
- `state/activity.jsonl` records activity and task changes
- `state/status.json` stores the current UI payload used by the extension
- `state/spans.jsonl` stores closed spans for stats
- `state/tracking.json` stores paused/resumed state
- `state/debug.jsonl` stores debug events when `WAID_DEBUG=1`
```

Update config references from `~/.config/waid/config.yaml` to `~/.waid/config.yaml`.

- [ ] **Step 4: Run tests**

```bash
uv run python -m unittest discover -s tests -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "Complete state dir consolidation to ~/.waid/"
```

---

### Task 2: Add screenshot config and models

**Files:**
- Modify: `src/waid/config.py`
- Modify: `src/waid/models.py`
- Modify: `config.example.yaml`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add `ScreenshotConfig` to config.py**

Add after `ClassifierConfig`:

```python
class ScreenshotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_retention: int = 50
```

Add `screenshot: ScreenshotConfig = Field(default_factory=ScreenshotConfig)` to `AppConfig`.

- [ ] **Step 2: Add `screenshot_path` to `ProviderState` in models.py**

Add the field to `ProviderState`:

```python
screenshot_path: str | None = None
```

- [ ] **Step 3: Add `screenshot` section to config.example.yaml**

After the `classifier` section, add:

```yaml
screenshot:
  enabled: true
  max_retention: 50
```

- [ ] **Step 4: Write tests for ScreenshotConfig**

In `tests/test_config.py`, add a test that `ScreenshotConfig` defaults are applied and that `AppConfig` parses a config with a `screenshot` section.

- [ ] **Step 5: Run tests**

```bash
uv run python -m unittest discover -s tests -v
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "Add ScreenshotConfig and screenshot_path model"
```

---

### Task 3: Add multimodal support to LLM client

**Files:**
- Modify: `src/waid/llm.py`
- Modify: `tests/test_llm.py`

- [ ] **Step 1: Add `build_vision_message()` to llm.py**

Add after the `LLMError` class:

```python
def build_vision_message(text: str, image_base64: str, media_type: str = "image/png") -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{image_base64}"},
            },
        ],
    }
```

- [ ] **Step 2: Widen `chat()` type hint**

Change the `messages` parameter type in `OpenAICompatibleClient.chat()` from `list[dict[str, str]]` to `list[dict[str, Any]]` to support vision message content arrays.

- [ ] **Step 3: Write test for `build_vision_message()`**

Add a test in `tests/test_llm.py`:

```python
def test_build_vision_message_structure(self):
    msg = build_vision_message("Describe this", "abcd1234")
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert len(msg["content"]) == 2
    assert msg["content"][0]["type"] == "text"
    assert msg["content"][0]["text"] == "Describe this"
    assert msg["content"][1]["type"] == "image_url"
    assert "base64,abcd1234" in msg["content"][1]["image_url"]["url"]
```

Don't forget to import `build_vision_message` in the test file.

- [ ] **Step 4: Run tests**

```bash
uv run python -m unittest discover -s tests -v
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "Add multimodal vision message support to LLM client"
```

---

### Task 4: Add vision classification to classifier

**Files:**
- Modify: `src/waid/defaults.py`
- Modify: `src/waid/classifier.py`
- Modify: `tests/test_classifier.py`

- [ ] **Step 1: Update `CLASSIFIER_BASE_PROMPT` in defaults.py**

Add after the existing rules:

```
- When a desktop screenshot is provided, use it as supplementary context. Rely primarily on text metadata and consult the screenshot only when it helps resolve ambiguity.
```

- [ ] **Step 2: Add `screenshot_path` param to `classify()`**

Add `screenshot_path: str | None = None` parameter to `EventClassifier.classify()`. When `screenshot_path` is not None and the config has screenshots enabled:

```python
import base64
from pathlib import Path

# Inside classify(), after building prompt:
if screenshot_path and config.screenshot.enabled:
    path = Path(screenshot_path)
    if path.exists():
        image_data = base64.b64encode(path.read_bytes()).decode("utf-8")
        vision_msg = build_vision_message(prompt, image_data)
        messages = [vision_msg]
    else:
        messages = [{"role": "user", "content": prompt}]
else:
    messages = [{"role": "user", "content": prompt}]
```

Then use `messages` instead of `[{"role": "user", "content": prompt}]` in `self.client.chat()` calls.

- [ ] **Step 3: Write tests**

Add tests for:
1. `classify()` with `screenshot_path=None` — text-only (existing behavior)
2. `classify()` with `screenshot_path` pointing to a real file — vision message is built
3. `classify()` with `screenshot_path` to a nonexistent file — falls back to text-only

- [ ] **Step 4: Run tests**

```bash
uv run python -m unittest discover -s tests -v
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "Add screenshot support to classifier"
```

---

### Task 5: Add screenshot processing and cleanup to daemon

**Files:**
- Modify: `src/waid/daemon.py`
- Modify: `tests/test_daemon.py`

- [ ] **Step 1: Pass `screenshot_path` through `_process_snapshot()`**

In `_process_snapshot()`, extract `screenshot_path` from `snapshot.state.screenshot_path` and pass to `classifier.classify()`:

```python
screenshot_path = getattr(snapshot.state, 'screenshot_path', None)
result = await self.classifier.classify(
    self.config,
    state,
    self.runtime.catalog,
    previous_result,
    screenshot_path=screenshot_path,
)
```

- [ ] **Step 2: Add `_cleanup_screenshots()` method**

```python
def _cleanup_screenshots(self) -> None:
    from .constants import SCREENSHOTS_DIR
    if not SCREENSHOTS_DIR.exists():
        return
    max_retention = self.config.screenshot.max_retention
    files = sorted(SCREENSHOTS_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime)
    if len(files) > max_retention:
        for old_file in files[:-max_retention]:
            old_file.unlink(missing_ok=True)
```

Call after classification in `_process_snapshot()`.

- [ ] **Step 3: Update `_log_raw_event()` to include `screenshot_path`**

Add `screenshot_path` to the raw event JSONL payload.

- [ ] **Step 4: Write tests**

Test that `screenshot_path` is passed through correctly and that `_cleanup_screenshots` removes old files.

- [ ] **Step 5: Run tests**

```bash
uv run python -m unittest discover -s tests -v
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "Add screenshot passthrough and cleanup to daemon"
```

---

### Task 6: Add screenshot capture to GNOME extension

**Files:**
- Modify: `extensions/gnome/extension.js`
- Modify: `src/waid/resources/gnome/extension.js`

- [ ] **Step 1: Add screenshot capture function**

Add a function to capture a screenshot using GNOME Shell's `Shell.Screenshot` API and save it to `~/.waid/screenshots/` with an ISO timestamp filename:

```javascript
function captureScreenshot(callback) {
    constScreenshot = new Shell.Screenshot();
    const now = new Date();
    const ts = now.toISOString().replace(/[:.]/g, '-');
    const dir = GLib.build_filenamev([WAID_DIR, 'screenshots']);
    const filepath = GLib.build_filenamev([dir, `${ts}.png`]);

    GLib.mkdir_with_parents(dir, 0o755);

    screenshot.screenshot(false, filepath, (success) => {
        if (success) {
            callback(filepath);
        } else {
            callback(null);
        }
    });
}
```

Note: The exact GNOME Shell Screenshot API varies by version. Use `global.display.screenshot()` or the `Shell.Screenshot` constructor depending on what's available. This step requires manual testing on a GNOME desktop.

- [ ] **Step 2: Integrate screenshot capture into state reporting**

Where the extension builds the state JSON for D-Bus, add a `screenshot_path` field. Call `captureScreenshot()` before emitting `StateChanged` and include the path (or null on failure) in the state payload.

- [ ] **Step 3: Update extension asset test assertions**

Update `tests/test_extension_assets.py` if needed to account for the new screenshot function.

- [ ] **Step 4: Manual testing documentation**

Document the GNOME extension screenshot feature and note that it requires manual testing on a GNOME desktop.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "Add screenshot capture to GNOME extension"
```

---

### Task 7: Update docs and config.example.yaml

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add screenshot/visual classification section to README**

Add a section explaining the `screenshot` config option and how visual classification works.

- [ ] **Step 2: Update AGENTS.md**

Add notes about the `screenshot` config section and the `~/.waid/screenshots/` directory.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "Update docs for visual classification and state dir"
```