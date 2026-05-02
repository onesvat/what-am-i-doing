# Visual Classification + Unified State Directory

## Overview

Two features delivered together:

1. **Visual classification**: GNOME extension captures desktop screenshots, daemon passes them to a vision-capable LLM for classification alongside text metadata.
2. **Unified state directory**: All waid data moves from `~/.config/waid/` + `~/.local/state/waid/` to `~/.waid/`.

## Motivation

- Text-only classification (window title, wm_class, app_id) can't distinguish ambiguous cases (e.g., a terminal showing a code repo vs. a terminal running a server). A screenshot gives the model visual context.
- The current XDG split (`~/.config/` + `~/.local/state/`) makes waid data hard to find. `~/.waid/` consolidates everything.

## Architecture

### Screenshot Flow

```
GNOME Extension                        Daemon                        LLM
───────────────                        ──────                        ───
1. Window state changes
2. Capture screenshot via
   Shell.Screenshot API
3. Save to ~/.waid/screenshots/
   <timestamp>.png
4. Build state JSON with
   screenshot_path field
5. Emit StateChanged signal     →
                                    6. Debounce (1s)
                                    7. Read screenshot file
                                    8. Base64-encode image
                                    9. Build multimodal prompt
                                   10. POST to vision LLM     →
                                                                 11. Classification
                                                                      result
                                   12. Cleanup old screenshots
```

### Unified Directory Structure

```
~/.waid/
  config.yaml
  tasks.yaml
  state/
    raw-events.jsonl
    activity.jsonl
    spans.jsonl
    status.json
    tracking.json
    debug.jsonl
  screenshots/
    2026-05-02T14-30-01.png
    ...
```

## Feature Details

### 1. Screenshot Capture (Extension)

- Every `StateChanged` signal triggers a screenshot via GNOME Shell's Screenshot API
- Screenshots saved to `~/.waid/screenshots/<timestamp>.png`
- `screenshot_path` field added to state JSON sent via D-Bus
- Screenshot capture failures are logged but non-fatal (daemon falls back to text-only)

### 2. Screenshot Processing (Daemon)

- `_process_snapshot()` extracts `screenshot_path` from snapshot state
- Passes it to `classifier.classify()` as `screenshot_path` parameter
- After classification, calls `_cleanup_screenshots()` to retain only the last N screenshots (configurable via `screenshot.max_retention`, default 50)
- `_log_raw_event()` includes `screenshot_path` in JSONL entries
- If screenshot file is missing or unreadable, daemon proceeds with text-only classification

### 3. Vision Classification (Classifier)

- `classify()` receives optional `screenshot_path: str | None`
- If path exists and `config.screenshot.enabled` is True:
  - Reads file, base64-encodes
  - Builds multimodal message using OpenAI Vision API format
  - Sends both text prompt and image to vision model
- If no screenshot or `screenshot.enabled` is False: text-only (current behavior)
- Prompt guidance: "When a desktop screenshot is provided, use it as supplementary context. Rely primarily on text metadata and consult the screenshot only when it helps resolve ambiguity."

### 4. LLM Client Multimodal Support

- `OpenAICompatibleClient.chat()` accepts `messages: list[dict[str, Any]]`
- New helper `build_vision_message(text, image_base64, media_type)` constructs OpenAI Vision content array
- Both Ollama and cloud APIs use the same format

### 5. Config

```yaml
screenshot:
  enabled: true
  max_retention: 50
```

- `enabled`: Whether screenshots are captured and used for classification
- `max_retention`: Number of screenshots to keep before cleanup

### 6. State Directory Migration

- `constants.py`: All path constants repointed to `~/.waid/`
- `__main__.py`: `waid init` handles migration from legacy dirs if `~/.waid/` doesn't exist yet
- `storage.py`: `migrate_legacy_state()` copies files from old dirs to new
- Extension JS: Path constants updated
- Legacy dirs (`~/.config/waid/`, `~/.local/state/waid/`) are not deleted after migration

### 7. Decision Cache

- `_decision_key()` excludes screenshot path from hash (classification should be based on content, not file path)
- If screenshot content changes classification, cache miss naturally occurs via state metadata changes

## Error Handling

- Screenshot capture failure in extension: log warning, send state without `screenshot_path`
- Screenshot file missing in daemon: fall back to text-only classification
- Vision model API error: fall back to text-only classification (retry logic already exists)
- `screenshot.enabled = False`: skip all screenshot processing

## File Change Summary

| File | Change |
|------|--------|
| `src/waid/constants.py` | Repoint paths to `~/.waid/`, add `SCREENSHOTS_DIR`, `LEGACY_*` constants |
| `src/waid/config.py` | Add `ScreenshotConfig`, update path references |
| `src/waid/models.py` | Add `screenshot_path` to `ProviderState` |
| `src/waid/llm.py` | Add `build_vision_message()`, widen `chat()` type hint |
| `src/waid/classifier.py` | Add `screenshot_path` param, multimodal message building |
| `src/waid/defaults.py` | Update `CLASSIFIER_BASE_PROMPT` with screenshot guidance |
| `src/waid/daemon.py` | Pass screenshot to classifier, add cleanup logic |
| `src/waid/__main__.py` | Migration logic, updated `waid init` |
| `src/waid/storage.py` | `migrate_legacy_state()` |
| `extension.js` (both copies) | Screenshot capture, path updates |
| `config.example.yaml` | Add `screenshot` section |
| `README.md` | Path updates, screenshot docs |
| `AGENTS.md` | Path convention updates |