# Package Rename: what_am_i_doing → waid

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the Python package from `what_am_i_doing` to `waid` across the entire codebase, making CLI name, package name, and import name consistent.

**Architecture:** Directory rename `src/what_am_i_doing/` → `src/waid/`, then update all references in pyproject.toml, source string literals, test imports, standalone scripts, and documentation. No functional changes — pure rename.

**Tech Stack:** Python 3.12, setuptools, uv

---

### Task 1: Rename the package directory and remove old egg-info

**Files:**
- Move: `src/what_am_i_doing/` → `src/waid/`
- Delete: `src/waid.egg-info/`

- [ ] **Step 1: Move the package directory**

```bash
mv src/what_am_i_doing src/waid
```

- [ ] **Step 2: Remove old egg-info (will be regenerated)**

```bash
rm -rf src/waid.egg-info
```

- [ ] **Step 3: Verify the move succeeded**

```bash
ls src/waid/__init__.py
```

Expected: file exists

---

### Task 2: Update pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update entry point and package-data**

In `pyproject.toml`, change:

Line 20: `waid = "what_am_i_doing.__main__:main"` → `waid = "waid.__main__:main"`
Line 30: `what_am_i_doing = [...]` → `waid = [...]`

- [ ] **Step 2: Reinstall the package**

```bash
uv sync
```

- [ ] **Step 3: Verify CLI still works**

```bash
uv run waid --help
```

Expected: help output shown

---

### Task 3: Update string references in source files

**Files:**
- Modify: `src/waid/resources.py`
- Modify: `src/waid/service.py`

- [ ] **Step 1: Update resources.py**

In `src/waid/resources.py`, change both occurrences:
- Line 8: `files("what_am_i_doing")` → `files("waid")`
- Line 15: `files("what_am_i_doing")` → `files("waid")`

- [ ] **Step 2: Update service.py**

In `src/waid/service.py`, line 24:
`"-m", "what_am_i_doing",` → `"-m", "waid",`

- [ ] **Step 3: Verify import works**

```bash
uv run python -c "from waid.constants import APP_NAME; print(APP_NAME)"
```

Expected: `waid`

---

### Task 4: Update all test imports and references

**Files:**
- Modify: `tests/test_classifier.py`
- Modify: `tests/test_cli_main.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_daemon.py`
- Modify: `tests/test_dbus_service.py`
- Modify: `tests/test_service.py`
- Modify: `tests/test_llm.py`
- Modify: `tests/test_gnome_provider.py`
- Modify: `tests/test_extension_assets.py`

- [ ] **Step 1: Update test_classifier.py**

Replace all `from what_am_i_doing` with `from waid`:
- Line 13: `from what_am_i_doing.classifier import EventClassifier` → `from waid.classifier import EventClassifier`
- Line 14: `from what_am_i_doing.config import AppConfig` → `from waid.config import AppConfig`
- Line 15: `from what_am_i_doing.constants import UNKNOWN_PATH` → `from waid.constants import UNKNOWN_PATH`
- Line 16: `from what_am_i_doing.models import (` → `from waid.models import (`

- [ ] **Step 2: Update test_cli_main.py**

- Line 13: `from what_am_i_doing.__main__ import _run_init, build_parser` → `from waid.__main__ import _run_init, build_parser`

- [ ] **Step 3: Update test_config.py**

- Line 14: `from what_am_i_doing.config import (` → `from waid.config import (`
- Line 21: `from what_am_i_doing.activity_catalog import builtin_activity_entries` → `from waid.activity_catalog import builtin_activity_entries`
- Line 22: `from what_am_i_doing.models import CatalogEntry` → `from waid.models import CatalogEntry`

- [ ] **Step 4: Update test_daemon.py**

- Line 15: `from what_am_i_doing.constants import DEBOUNCE_SECONDS` → `from waid.constants import DEBOUNCE_SECONDS`
- Line 16: `from what_am_i_doing.daemon import describe_catalog_reload` → `from waid.daemon import describe_catalog_reload`
- Line 17: `from what_am_i_doing.models import (` → `from waid.models import (`
- Line 48: `with patch("what_am_i_doing.daemon.GnomeProvider"):` → `with patch("waid.daemon.GnomeProvider"):`
- Line 49: `with patch("what_am_i_doing.daemon.DaemonDBusService"):` → `with patch("waid.daemon.DaemonDBusService"):`
- Line 50: `with patch("what_am_i_doing.daemon.load_config") as mock_load:` → `with patch("waid.daemon.load_config") as mock_load:`
- Line 51: `with patch("what_am_i_doing.daemon.load_tasks") as mock_tasks:` → `with patch("waid.daemon.load_tasks") as mock_tasks:`
- Line 54: `with patch("what_am_i_doing.daemon.load_status")` → `with patch("waid.daemon.load_status")`
- Line 56: `from what_am_i_doing.daemon import ActivityDaemon` → `from waid.daemon import ActivityDaemon`
- Line 57: `from what_am_i_doing.config import AppConfig` → `from waid.config import AppConfig`

- [ ] **Step 5: Update test_dbus_service.py**

- Line 14: `from what_am_i_doing.dbus_service import DaemonInterface, _disconnect_bus` → `from waid.dbus_service import DaemonInterface, _disconnect_bus`
- Line 15: `from what_am_i_doing.models import (` → `from waid.models import (`

- [ ] **Step 6: Update test_service.py**

- Line 12: `from what_am_i_doing.service import render_unit` → `from waid.service import render_unit`
- Line 18: `self.assertIn("-m what_am_i_doing --config", unit)` → `self.assertIn("-m waid --config", unit)`

- [ ] **Step 7: Update test_llm.py**

- Line 13: `from what_am_i_doing.llm import OpenAICompatibleClient` → `from waid.llm import OpenAICompatibleClient`

- [ ] **Step 8: Update test_gnome_provider.py**

- Line 14: `from what_am_i_doing.providers.gnome import GnomeProvider` → `from waid.providers.gnome import GnomeProvider`

- [ ] **Step 9: Update test_extension_assets.py**

- Line 15: `source = (ROOT / "src/what_am_i_doing/resources/gnome/extension.js").read_text(` → `source = (ROOT / "src/waid/resources/gnome/extension.js").read_text(`

- [ ] **Step 10: Run all tests**

```bash
uv run python -m unittest discover -s tests -v
```

Expected: All tests pass

---

### Task 5: Update standalone scripts and documentation

**Files:**
- Modify: `sp-generate-tasks.py`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `skills/waid-train/SKILL.md`

- [ ] **Step 1: Update sp-generate-tasks.py**

- Line 18: `from what_am_i_doing.config import default_config_path, default_tasks_path, load_config` → `from waid.config import default_config_path, default_tasks_path, load_config`
- Line 19: `from what_am_i_doing.llm import OpenAICompatibleClient` → `from waid.llm import OpenAICompatibleClient`

- [ ] **Step 2: Update README.md**

Update path references from `~/.config/waid/` (these will change with the state dir feature later, but for now they should reflect the current behavior). No `what_am_i_doing` references exist in README content, but confirm no stale package name references.

- [ ] **Step 3: Verify no remaining references**

```bash
rg "what_am_i_doing" --type py src/ tests/ sp-generate-tasks.py
rg "what_am_i_doing" --type toml pyproject.toml
```

Expected: No results (except possibly in metadata.json URL which is the repo name)

---

### Task 6: Commit

- [ ] **Step 1: Stage all changes**

```bash
git add -A
```

- [ ] **Step 2: Verify staged changes look correct**

```bash
git diff --cached --stat
```

Expected: Package directory moved, all source/test/doc files updated, no `what_am_i_doing` references remaining

- [ ] **Step 3: Commit**

```bash
git commit -m "Rename Python package from what_am_i_doing to waid"
```

- [ ] **Step 4: Run full verification**

```bash
uv run python -m unittest discover -s tests -v
uv run waid --help
```

Expected: All tests pass, CLI works