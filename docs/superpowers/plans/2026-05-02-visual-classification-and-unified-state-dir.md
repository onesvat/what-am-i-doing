# Visual Classification + Unified State Dir Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add visual classification via screenshots and consolidate state directory to `~/.waid/`.

**Architecture:** Extension captures screenshots → saves to `~/.waid/screenshots/` → sends path via D-Bus → daemon passes to classifier → classifier uses vision model when available → daemon cleans up old screenshots. All paths consolidated under `~/.waid/`.

**Tech Stack:** Python 3.12, Pydantic, GNOME Shell Screenshot API, OpenAI Vision API format

---

### Task 1: Consolidate state dir to ~/.waid/

**Files:**
- Modify: `src/waid/constants.py`
- Modify: `src/waid/__main__.py`
- Modify: `src/waid/config.py`
- Modify: `src/waid/storage.py`
- Modify: `extensions/gnome/extension.js`
- Modify: `src/waid/resources/gnome/extension.js`
- Modify: `README.md`
- Modify: `tests/test_extension_assets.py`
- Modify: `tests/test_service.py`
- Modify: `tests/test_cli_main.py`

- [ ] **Step 1:** Update `constants.py` — repoint paths to `~/.waid/`, add `SCREENSHOTS_DIR` and legacy constants
- [ ] **Step 2:** Update `__main__.py` — init creates new dirs, adds migration from legacy dirs
- [ ] **Step 3:** Update `config.py` — path references in comments/strings
- [ ] **Step 4:** Add `migrate_legacy_state()` to `storage.py`
- [ ] **Step 5:** Update both `extension.js` copies — `STATE_DIR` and `CONFIG_FILE` paths
- [ ] **Step 6:** Update `README.md` — all path references
- [ ] **Step 7:** Update tests — path assertions, migration tests
- [ ] **Step 8:** Run tests and verify
- [ ] **Step 9:** Commit

---

### Task 2: Add screenshot config and models

**Files:**
- Modify: `src/waid/config.py`
- Modify: `src/waid/models.py`
- Modify: `config.example.yaml`
- Modify: `tests/test_config.py`

- [ ] **Step 1:** Add `ScreenshotConfig` to `config.py` and wire into `AppConfig`
- [ ] **Step 2:** Add `screenshot_path: str | None = None` to `ProviderState` in `models.py`
- [ ] **Step 3:** Add `screenshot` section to `config.example.yaml`
- [ ] **Step 4:** Write tests for `ScreenshotConfig` defaults and parsing
- [ ] **Step 5:** Run tests and verify
- [ ] **Step 6:** Commit

---

### Task 3: Add multimodal support to LLM client

**Files:**
- Modify: `src/waid/llm.py`
- Modify: `tests/test_llm.py`

- [ ] **Step 1:** Add `build_vision_message()` helper to `llm.py`
- [ ] **Step 2:** Widen `chat()` type hint to `list[dict[str, Any]]`
- [ ] **Step 3:** Write test for `build_vision_message()`
- [ ] **Step 4:** Run tests and verify
- [ ] **Step 5:** Commit

---

### Task 4: Add vision classification to classifier

**Files:**
- Modify: `src/waid/defaults.py`
- Modify: `src/waid/classifier.py`
- Modify: `tests/test_classifier.py`

- [ ] **Step 1:** Update `CLASSIFIER_BASE_PROMPT` with screenshot guidance
- [ ] **Step 2:** Add `screenshot_path` param to `classify()`, base64 image loading, multimodal message building
- [ ] **Step 3:** Write tests: with screenshot, without screenshot, screenshot disabled
- [ ] **Step 4:** Run tests and verify
- [ ] **Step 5:** Commit

---

### Task 5: Add screenshot processing and cleanup to daemon

**Files:**
- Modify: `src/waid/daemon.py`
- Modify: `tests/test_daemon.py`

- [ ] **Step 1:** `_process_snapshot()` extracts `screenshot_path` and passes to classifier
- [ ] **Step 2:** Add `_cleanup_screenshots()` retaining last N files
- [ ] **Step 3:** Update `_log_raw_event()` to include `screenshot_path`
- [ ] **Step 4:** Write tests for screenshot passthrough, cleanup, and text-only fallback
- [ ] **Step 5:** Run tests and verify
- [ ] **Step 6:** Commit

---

### Task 6: Add screenshot capture to GNOME extension

**Files:**
- Modify: `extensions/gnome/extension.js`
- Modify: `src/waid/resources/gnome/extension.js`
- Modify: `tests/test_extension_assets.py`

- [ ] **Step 1:** Add screenshot capture to extension using GNOME Shell Screenshot API
- [ ] **Step 2:** Save screenshots to `~/.waid/screenshots/` with timestamp filenames
- [ ] **Step 3:** Add `screenshot_path` to state JSON payload
- [ ] **Step 4:** Handle screenshot failures gracefully
- [ ] **Step 5:** Update extension asset test assertions
- [ ] **Step 6:** Manual testing verification steps documented
- [ ] **Step 7:** Commit

---

### Task 7: Update docs and README

**Files:**
- Modify: `README.md`
- Modify: `config.example.yaml`
- Modify: `AGENTS.md`

- [ ] **Step 1:** Add screenshot/visual classification section to README
- [ ] **Step 2:** Update directory structure in README
- [ ] **Step 3:** Update AGENTS.md with new path conventions and screenshot feature notes
- [ ] **Step 4:** Commit