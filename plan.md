# what-am-i-doing: Activity Tracker Plan

## Context

Build a modular activity tracker for Linux desktops. Two separate components:

1. **Desktop provider** (per-DE) - collects raw window/environment data, exposes it via a standard interface
2. **Core daemon** (DE-agnostic) - consumes provider data, classifies via LLM, fires user-configured actions

These are fully decoupled. The provider knows nothing about classification or actions. The daemon knows nothing about GNOME or Hyprland.

## Part 1: GNOME Shell Extension Design

We write our **own** GNOME Shell extension (`what-am-i-doing@gnome`) that exposes rich data via D-Bus. This gives us full control over what we collect.

### D-Bus Interface: `org.whatamidoing.WindowTracker`

**Bus name:** `org.whatamidoing.WindowTracker`
**Object path:** `/org/whatamidoing/WindowTracker`

#### Method: `GetCurrentState() -> String (JSON)`

Returns a JSON object with everything the extension can see:

```json
{
  "focused_window": {
    "title": "api.py - my-project - Visual Studio Code",
    "wm_class": "code",
    "wm_class_instance": "code",
    "pid": 12345,
    "workspace": 1,
    "workspace_name": "Main",
    "monitor": "DP-1",
    "monitor_index": 0,
    "fullscreen": false,
    "maximized": true,
    "above": false,
    "geometry": { "x": 0, "y": 0, "width": 1920, "height": 1080 }
  },
  "open_windows": [
    { "title": "...", "wm_class": "...", "workspace": 1 },
    { "title": "...", "wm_class": "...", "workspace": 2 }
  ],
  "active_workspace": 1,
  "workspace_count": 4,
  "screen_locked": false,
  "timestamp": 1712300000
}
```

#### Signal: `WindowChanged(String json)`

Emitted on every focus change. Payload is the same `focused_window` object. This enables event-driven mode (Phase 2) without polling.

#### Signal: `WorkspaceChanged(Int workspace_number)`

Emitted when the user switches workspaces.

### What the extension collects (and why)

| Data | Source in GNOME JS | Why useful |
|------|-------------------|------------|
| `title` | `global.display.focus_window.get_title()` | Primary signal for classification |
| `wm_class` | `meta_window.get_wm_class()` | App identification (firefox, code, kitty) |
| `wm_class_instance` | `meta_window.get_wm_class_instance()` | Distinguishes app profiles |
| `pid` | `meta_window.get_pid()` | Link to process (can read /proc/pid/cmdline) |
| `workspace` | `meta_window.get_workspace().index()` | Context grouping |
| `workspace_name` | workspace meta if available | Human-readable workspace |
| `monitor` | `meta_window.get_monitor()` + display info | Multi-monitor awareness |
| `fullscreen` | `meta_window.is_fullscreen()` | Indicates focused activity (video, gaming) |
| `maximized` | `meta_window.get_maximized()` | Window state |
| `geometry` | `meta_window.get_frame_rect()` | Window size/position |
| `open_windows` | `global.get_window_actors()` | Full context of what's open |
| `screen_locked` | `Main.screenShield.locked` | Skip tracking when locked |

### Extension file structure

```
extensions/gnome/
├── metadata.json          # Extension metadata (uuid, gnome-shell-version)
├── extension.js           # Main extension code
└── schemas/
    └── org.whatamidoing.gschema.xml  # (if settings needed)
```

### Extension tech notes

- Written in GJS (GNOME JavaScript), the standard for GNOME Shell extensions
- Registers D-Bus interface on `enable()`, unregisters on `disable()`
- Connects to `global.display.connect('notify::focus-window', ...)` for window change events
- Connects to `global.workspace_manager.connect('active-workspace-changed', ...)` for workspace events
- Minimal footprint: no polling inside the extension, purely event-driven + on-demand D-Bus method

---

## Part 2: Core Daemon Design

### Data flow

```
Provider (polls or listens to D-Bus)
    │
    ▼
Raw WindowInfo + MediaInfo + IdleState
    │
    ▼
Activity Log (ALWAYS logs every change to JSONL)
    │
    ▼
Change Detector (did context meaningfully change?)
    │ yes
    ▼
Classifier (LLM: categorize from user-configured list)
    │
    ▼
Action Runner (fires all enabled actions with old + new state)
    │
    ├──▶ HomeAssistant action
    ├──▶ Todoist action
    ├──▶ Webhook action
    ├──▶ StateFile action
    ├──▶ Command action
    └──▶ ... (user can add more)
```

### Provider abstraction (DE separation)

```python
class Provider(ABC):
    """Each DE implements this. The daemon doesn't know which DE is running."""

    @abstractmethod
    def get_state(self) -> ProviderState:
        """Return current window + environment state."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Can this provider work on the current system?"""
        ...
```

`ProviderState` is the common model:

```python
class WindowInfo(BaseModel):
    title: str
    wm_class: str
    pid: int
    workspace: int | None = None
    monitor: str | None = None
    fullscreen: bool = False
    maximized: bool = False
    geometry: dict | None = None

class ProviderState(BaseModel):
    focused_window: WindowInfo | None
    open_windows: list[WindowInfo] = []
    screen_locked: bool = False
    timestamp: datetime
```

Providers implemented:
- **gnome.py** - calls our GNOME extension via D-Bus (`org.whatamidoing.WindowTracker.GetCurrentState`)
- **hyprland.py** - `hyprctl activewindow -j`
- **sway.py** - `swaymsg -t get_tree`
- **x11.py** - `xdotool` fallback
- Auto-detected via env vars (`XDG_CURRENT_DESKTOP`, `HYPRLAND_INSTANCE_SIGNATURE`, `SWAYSOCK`)

### Action system (fully user-configurable)

```python
class Action(ABC):
    """Each output plugin implements this."""

    @abstractmethod
    def on_activity_change(self, old: ActivityState | None, new: ActivityState) -> None:
        """Called when the classified activity changes."""
        ...

    def on_window_change(self, old: WindowInfo | None, new: WindowInfo) -> None:
        """Called on every window switch. Override if you care about raw switches."""
        pass
```

Two hooks: `on_activity_change` (after LLM classification) and `on_window_change` (raw, every switch). Actions choose which to implement.

Each `[[actions]]` block in config creates one action instance. All config keys beyond `type` and `enabled` are passed to the action as its config dict.

```toml
[[actions]]
type = "homeassistant"
enabled = true
url = "http://homeassistant.local:8123"
token = "your-token"
entity_id = "sensor.current_activity"
# user can add any keys their action needs

[[actions]]
type = "todoist"
enabled = false
api_key = "your-key"
project_id = "12345"

[[actions]]
type = "command"
enabled = true
on = "activity_change"          # or "window_change" or "both"
command = "notify-send '{category}: {task}'"

[[actions]]
type = "webhook"
enabled = false
url = "https://example.com/hook"
headers = { "X-Custom" = "value" }
```

Built-in actions:
| Action | Trigger | What it does |
|--------|---------|-------------|
| `statefile` | activity_change | Writes `current.json` |
| `log` | both | Appends to `activity.jsonl` (every window switch AND classification) |
| `homeassistant` | activity_change | `POST /api/states/{entity_id}` |
| `todoist` | activity_change | Updates active Todoist task |
| `webhook` | configurable | POSTs JSON to URL |
| `command` | configurable | Runs shell command with `{task}`, `{category}`, `{title}`, `{wm_class}` template vars |

### Classifier (user-configurable categories & tasks)

```toml
[classifier]
# Categories the LLM picks from. Fully customizable.
categories = [
    { name = "coding", description = "Writing or reading code" },
    { name = "code-review", description = "Reviewing pull requests" },
    { name = "browsing", description = "General web browsing" },
    { name = "communication", description = "Email, chat, video calls" },
    { name = "media", description = "Watching video, listening to music" },
    { name = "writing", description = "Writing documents, notes" },
    { name = "productivity", description = "Planning, task management" },
    { name = "gaming", description = "Playing games" },
    { name = "system", description = "System settings, file management" },
]

# Optional: predefined tasks the LLM can assign to.
# If empty, LLM generates free-form task descriptions.
tasks = [
    { name = "what-am-i-doing", description = "Working on the activity tracker project" },
    { name = "telaffuz", description = "Working on the pronunciation app" },
]

# Optional: rules to help the classifier (app -> category hints)
[[classifier.rules]]
wm_class = "code"
hint = "Usually coding unless the title suggests otherwise"

[[classifier.rules]]
wm_class = "firefox"
title_contains = "YouTube"
hint = "This is media consumption"
```

The classifier prompt is built dynamically from this config:

```
You are an activity classifier. Given the user's recent window activity, determine what they are doing.

## Available categories
{for cat in categories}
- {cat.name}: {cat.description}
{endfor}

{if tasks}
## Known tasks (pick one if it matches, otherwise describe freely)
{for task in tasks}
- {task.name}: {task.description}
{endfor}
{endif}

## Recent window activity (most recent first)
{buffer_entries}

{if media}
## Currently playing
{artist} - {track} on {player} ({playback_status})
{endif}

Respond with JSON: {"task": "...", "category": "..."}
```

### Activity logging (every change)

Two levels of logging, both to JSONL:

1. **Window log** - every focus change, raw data, no LLM involved:
```json
{"ts": "2026-04-05T14:32:00", "event": "window_change", "title": "...", "wm_class": "code", "pid": 123, "workspace": 1}
```

2. **Activity log** - every classification change:
```json
{"ts": "2026-04-05T14:32:05", "event": "activity_change", "task": "Working on API", "category": "coding", "window_title": "api.py - ...", "wm_class": "code"}
```

Both written by the built-in `log` action. The window log is always-on (even without LLM), providing raw data for later analysis.

### Extras

- **Idle detection**: `org.gnome.Mutter.IdleMonitor.GetIdletime` (GNOME), generic fallback for other DEs
- **MPRIS media**: detect currently playing media via `org.mpris.MediaPlayer2.*` D-Bus. Returns `MediaInfo(player, artist, title, album, status)`

---

## Full config example

```toml
poll_interval = 15               # seconds between polls
idle_threshold = 300             # seconds before marking idle
state_dir = "~/.local/state/what-am-i-doing"

# Auto-detected if not set
# provider = "gnome"

[llm]
base_url = "http://localhost:11434/v1"
model = "gemma3:4b"
api_key = ""                     # empty for Ollama

[classifier]
categories = [
    { name = "coding", description = "Writing or reading code" },
    { name = "browsing", description = "General web browsing" },
    { name = "communication", description = "Email, chat, video calls" },
    { name = "media", description = "Video, music, streaming" },
    { name = "writing", description = "Documents, notes, articles" },
    { name = "productivity", description = "Planning, task management" },
    { name = "gaming", description = "Playing games" },
    { name = "system", description = "Settings, file management, terminal admin" },
]
tasks = []

[[actions]]
type = "statefile"
enabled = true

[[actions]]
type = "log"
enabled = true

[[actions]]
type = "homeassistant"
enabled = false
url = "http://homeassistant.local:8123"
token = "your-long-lived-access-token"
entity_id = "sensor.current_activity"

[[actions]]
type = "command"
enabled = false
on = "activity_change"
command = "notify-send 'Now: {category} - {task}'"
```

---

## Project Structure

```
what-am-i-doing/
├── pyproject.toml
├── config.example.toml
├── extensions/                      # Desktop-specific extensions (separate from core)
│   └── gnome/
│       ├── metadata.json
│       └── extension.js
├── systemd/
│   └── what-am-i-doing.service
└── src/what_am_i_doing/
    ├── __init__.py
    ├── __main__.py                  # CLI: run, status, log, check
    ├── config.py                    # TOML config + pydantic validation
    ├── models.py                    # WindowInfo, ActivityState, MediaInfo, ProviderState
    ├── tracker.py                   # Main loop, buffer, change detection
    ├── classifier.py                # LLM prompt builder + openai SDK call
    ├── providers/
    │   ├── __init__.py              # Auto-detect + registry
    │   ├── base.py                  # Abstract Provider
    │   ├── gnome.py                 # D-Bus to our extension
    │   ├── hyprland.py              # hyprctl
    │   ├── sway.py                  # swaymsg
    │   └── x11.py                   # xdotool
    ├── actions/
    │   ├── __init__.py              # Registry + runner
    │   ├── base.py                  # Abstract Action
    │   ├── homeassistant.py
    │   ├── todoist.py
    │   ├── webhook.py
    │   ├── statefile.py
    │   ├── log.py
    │   └── command.py
    └── extras/
        ├── idle.py
        └── mpris.py
```

---

## Implementation Order

1. **Models + config** - pydantic models, TOML loading, config validation
2. **GNOME Shell extension** - extension.js with D-Bus interface, GetCurrentState + WindowChanged signal
3. **GNOME provider** - Python side, calls extension via gdbus
4. **Tracker loop** - poll provider, maintain buffer, detect changes
5. **Log action** - JSONL logging of every window switch (works without LLM)
6. **StateFile action** - write current.json
7. **Classifier** - LLM classification with user-configured categories/tasks
8. **HomeAssistant action**
9. **Webhook + command actions**
10. **CLI subcommands** (status, log, check)
11. **Idle detection + MPRIS**
12. **Todoist action**
13. **systemd service**
14. **Hyprland/Sway/X11 providers** (on demand)

## Dependencies

- `openai` - LLM calls via OpenAI-compatible API (Ollama, OpenAI, Gemini, etc.)
- `requests` - HTTP calls for actions
- `pydantic` - config and data model validation
- stdlib only: `tomllib`, `subprocess`, `json`, `pathlib`, `datetime`, `hashlib`, `logging`
