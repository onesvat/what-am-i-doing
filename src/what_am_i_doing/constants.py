from __future__ import annotations

from pathlib import Path


APP_NAME = "waid"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.yaml"
TASKS_PATH = CONFIG_DIR / "tasks.yaml"
STATE_DIR = Path.home() / ".local" / "state" / APP_NAME
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
SERVICE_NAME = f"{APP_NAME}.service"
EXTENSION_UUID = f"{APP_NAME}@onesvat.github.io"
LEGACY_EXTENSION_UUIDS = ("waid@gnome",)
EXTENSION_DIR = (
    Path.home() / ".local" / "share" / "gnome-shell" / "extensions" / EXTENSION_UUID
)

TRACKER_BUS_NAME = "org.waid.WindowTracker"
TRACKER_OBJECT_PATH = "/org/waid/WindowTracker"
TRACKER_INTERFACE = "org.waid.WindowTracker"

DAEMON_BUS_NAME = "org.waid.Daemon"
DAEMON_OBJECT_PATH = "/org/waid/Daemon"
DAEMON_INTERFACE = "org.waid.Daemon"

PANEL_SCHEMA_VERSION = 1
PANEL_KIND_CLASSIFIED = "classified"
PANEL_KIND_UNCLASSIFIED = "unclassified"
PANEL_KIND_DISCONNECTED = "disconnected"
PANEL_KIND_PAUSED = "paused"
UNKNOWN_PATH = "unknown"
RESERVED_PATHS = {
    "unknown",
    "idle",
    PANEL_KIND_CLASSIFIED,
    PANEL_KIND_UNCLASSIFIED,
    PANEL_KIND_DISCONNECTED,
    PANEL_KIND_PAUSED,
}
RESERVED_CATEGORY_NAMES = RESERVED_PATHS
IDLE_ICON = "system-suspend-symbolic"
UNCLASSIFIED_ICON = "help-about-symbolic"
DISCONNECTED_ICON = "network-offline-symbolic"
PAUSED_ICON = "media-playback-pause-symbolic"
DEBUG_ENV_VAR = "WAID_DEBUG"
DEBOUNCE_SECONDS = 1.0
