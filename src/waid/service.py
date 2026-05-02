from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import sys

from .constants import CONFIG_PATH, SERVICE_NAME, SYSTEMD_USER_DIR
from .resources import resource_text


def unit_path() -> Path:
    return SYSTEMD_USER_DIR / SERVICE_NAME


def render_unit(config_path: Path | None = None) -> str:
    template = resource_text("systemd", "waid.service.in")
    effective_config = (config_path or CONFIG_PATH).expanduser()
    exec_start = " ".join(
        shlex.quote(part)
        for part in (
            sys.executable,
            "-m",
            "waid",
            "--config",
            str(effective_config),
            "run",
        )
    )
    return template.replace("{{ exec_start }}", exec_start)


def install_unit(config_path: Path | None = None) -> Path:
    path = unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_unit(config_path), encoding="utf-8")
    return path


def run_systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def run_journalctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["journalctl", "--user", "-u", SERVICE_NAME, *args],
        check=False,
        capture_output=True,
        text=True,
    )
