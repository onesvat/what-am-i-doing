from __future__ import annotations

from pathlib import Path


APP_NAME = "waid"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.yaml"
STATE_DIR = Path.home() / ".local" / "state" / APP_NAME
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
SERVICE_NAME = f"{APP_NAME}.service"
EXTENSION_UUID = f"{APP_NAME}@onesvat.github.io"
LEGACY_EXTENSION_UUIDS = ("waid@gnome",)
EXTENSION_DIR = Path.home() / ".local" / "share" / "gnome-shell" / "extensions" / EXTENSION_UUID

TRACKER_BUS_NAME = "org.waid.WindowTracker"
TRACKER_OBJECT_PATH = "/org/waid/WindowTracker"
TRACKER_INTERFACE = "org.waid.WindowTracker"

DAEMON_BUS_NAME = "org.waid.Daemon"
DAEMON_OBJECT_PATH = "/org/waid/Daemon"
DAEMON_INTERFACE = "org.waid.Daemon"

FALLBACK_CATEGORY = "unknown"
DEBUG_ENV_VAR = "WAID_DEBUG"
