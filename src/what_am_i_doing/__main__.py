from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from dbus_next.errors import DBusError

from .config import (
    build_minimal_config,
    default_config_path,
    load_config,
    render_config,
)
from .constants import CONFIG_DIR, CONFIG_PATH, EXTENSION_DIR, EXTENSION_UUID, SERVICE_NAME
from .daemon import ActivityDaemon
from .dbus_service import daemon_refresh_taxonomy, daemon_status_json
from .models import AppPaths
from .resources import copy_resource_tree
from .service import install_unit, run_journalctl, run_systemctl, unit_path
from .storage import load_spans, load_status
from .wizard import run_init_wizard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="waid")
    parser.add_argument("--config", default=str(default_config_path()), help="Path to config file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing config")

    subparsers.add_parser("run")
    refresh_parser = subparsers.add_parser("refresh")
    refresh_parser.add_argument("--local", action="store_true", help="Refresh without D-Bus")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    stats_parser = subparsers.add_parser("stats")
    stats_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    subparsers.add_parser("doctor")

    config_parser = subparsers.add_parser("config")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("path")
    config_sub.add_parser("edit")
    config_sub.add_parser("validate")

    extension_parser = subparsers.add_parser("extension")
    extension_sub = extension_parser.add_subparsers(dest="extension_command", required=True)
    extension_sub.add_parser("install")
    extension_sub.add_parser("status")

    service_parser = subparsers.add_parser("service")
    service_sub = service_parser.add_subparsers(dest="service_command", required=True)
    install = service_sub.add_parser("install")
    install.add_argument("--now", action="store_true", help="Enable and start after install")
    service_sub.add_parser("uninstall")
    service_sub.add_parser("start")
    service_sub.add_parser("stop")
    service_sub.add_parser("restart")
    service_sub.add_parser("status")
    logs = service_sub.add_parser("logs")
    logs.add_argument("--lines", type=int, default=100)
    logs.add_argument("--follow", action="store_true")

    return parser


async def _run_daemon(config_path: str) -> None:
    config = load_config(config_path)
    daemon = ActivityDaemon(config)
    await daemon.run()


async def _run_refresh(config_path: str, *, local: bool) -> None:
    if not local:
        try:
            await daemon_refresh_taxonomy()
            print("taxonomy refreshed via daemon")
            return
        except (DBusError, RuntimeError):
            pass
    config = load_config(config_path)
    daemon = ActivityDaemon(config)
    await daemon.refresh_taxonomy()
    print("taxonomy refreshed locally")


async def _run_status(json_output: bool) -> None:
    payload: dict[str, object]
    try:
        payload = json.loads(await daemon_status_json())
        payload["source"] = "dbus"
    except (DBusError, RuntimeError, json.JSONDecodeError):
        status = load_status(AppPaths.default().status_json)
        payload = {
            "current_path": status.current_path if status else "unknown",
            "top_level": status.top_level if status else "unknown",
            "icon": status.icon if status else "help-about-symbolic",
            "updated_at": status.updated_at.isoformat() if status else None,
            "source": "state-file",
        }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"path: {payload['current_path']}")
    print(f"top level: {payload['top_level']}")
    print(f"icon: {payload['icon']}")
    if payload.get("updated_at"):
        print(f"updated: {payload['updated_at']}")
    print(f"source: {payload['source']}")


def _stats_payload() -> dict[str, dict[str, dict[str, float]]]:
    spans = load_spans(AppPaths.default().spans_log)
    now = datetime.now(tz=UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())
    month_start = day_start.replace(day=1)
    windows = {
        "all": None,
        "daily": day_start,
        "weekly": week_start,
        "monthly": month_start,
    }
    summary: dict[str, dict[str, dict[str, float]]] = {}
    for label, window_start in windows.items():
        by_top: dict[str, float] = {}
        by_path: dict[str, float] = {}
        for span in spans:
            if window_start is not None and span.ended_at < window_start:
                continue
            by_top[span.top_level] = by_top.get(span.top_level, 0.0) + span.duration_seconds
            by_path[span.path] = by_path.get(span.path, 0.0) + span.duration_seconds
        summary[label] = {"by_top": by_top, "by_path": by_path}
    return summary


def _run_stats(json_output: bool) -> None:
    payload = _stats_payload()
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for window, groups in payload.items():
        print(f"[{window}]")
        for path, seconds in sorted(groups["by_path"].items()):
            print(f"{path}: {seconds:.0f}s")


def _run_init(config_path: str, *, force: bool) -> None:
    path = Path(config_path).expanduser()
    if path.exists() and not force:
        raise SystemExit(f"config already exists at {path}; use --force to overwrite")
    answers = run_init_wizard()
    config = build_minimal_config(
        base_url=answers.base_url,
        model_name=answers.model_name,
        api_key_env=answers.api_key_env,
        category_notes=answers.category_notes,
        context_tools=answers.context_tools,
        action_tools=answers.action_tools,
        generator_instructions=answers.generator_instructions,
        classifier_instructions=answers.classifier_instructions,
        classifier_params=answers.classifier_params,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    AppPaths.default().state_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(render_config(config), encoding="utf-8")
    print(f"wrote config: {path}")
    print("next:")
    print("  waid extension install")
    print(f"  gnome-extensions enable {EXTENSION_UUID}")
    print("  waid service install --now")


def _run_config_command(args: argparse.Namespace) -> None:
    path = Path(args.config).expanduser()
    if args.config_command == "path":
        print(path)
        return
    if args.config_command == "validate":
        load_config(path)
        print(f"config ok: {path}")
        return
    if args.config_command == "edit":
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if editor is None:
            print(path)
            raise SystemExit("set $EDITOR or $VISUAL to use `waid config edit`")
        subprocess.run([editor, str(path)], check=False)
        return
    raise SystemExit(2)


def _run_extension_command(args: argparse.Namespace) -> None:
    if args.extension_command == "install":
        copy_resource_tree("gnome", destination=EXTENSION_DIR)
        print(f"installed extension to {EXTENSION_DIR}")
        print(f"enable with: gnome-extensions enable {EXTENSION_UUID}")
        return
    if args.extension_command == "status":
        print(f"extension dir: {EXTENSION_DIR}")
        print(f"installed: {'yes' if EXTENSION_DIR.exists() else 'no'}")
        proc = subprocess.run(
            ["gnome-extensions", "info", EXTENSION_UUID],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            print(proc.stdout.strip())
        else:
            print("gnome-extensions info unavailable or extension not enabled")
        return
    raise SystemExit(2)


def _run_service_command(args: argparse.Namespace) -> None:
    if args.service_command == "install":
        path = install_unit(Path(args.config).expanduser())
        print(f"installed user unit: {path}")
        run_systemctl("daemon-reload")
        if args.now:
            for action in (("enable", "--now", SERVICE_NAME),):
                proc = run_systemctl(*action)
                if proc.returncode != 0:
                    raise SystemExit(proc.stderr.strip() or proc.stdout.strip())
            print("service enabled and started")
        return
    if args.service_command == "uninstall":
        run_systemctl("disable", "--now", SERVICE_NAME)
        path = unit_path()
        if path.exists():
            path.unlink()
        run_systemctl("daemon-reload")
        print("service uninstalled")
        return
    if args.service_command in {"start", "stop", "restart", "status"}:
        proc = run_systemctl(args.service_command, SERVICE_NAME)
        output = proc.stdout.strip() or proc.stderr.strip()
        if output:
            print(output)
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)
        return
    if args.service_command == "logs":
        if args.follow:
            subprocess.run(
                ["journalctl", "--user", "-u", SERVICE_NAME, "-n", str(args.lines), "-f"],
                check=False,
            )
            return
        proc = run_journalctl("-n", str(args.lines), "--no-pager")
        output = proc.stdout.strip() or proc.stderr.strip()
        if output:
            print(output)
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)
        return
    raise SystemExit(2)


def _run_doctor(config_path: str) -> None:
    checks: list[tuple[str, str]] = []
    path = Path(config_path).expanduser()
    checks.append(("config", "ok" if path.exists() else "missing"))
    try:
        config = load_config(path)
        checks.append(("config-parse", "ok"))
        for name, tool in {**config.tools.context, **config.tools.actions}.items():
            checks.append((f"tool:{name}", "ok" if shutil.which(tool.run[0]) else "missing"))
    except Exception as exc:
        checks.append(("config-parse", f"error: {exc}"))
    checks.append(("gdbus", "ok" if shutil.which("gdbus") else "missing"))
    checks.append(("gnome-extensions", "ok" if shutil.which("gnome-extensions") else "missing"))
    checks.append(("systemctl", "ok" if shutil.which("systemctl") else "missing"))
    checks.append(("extension", "ok" if EXTENSION_DIR.exists() else "missing"))
    checks.append(("service-unit", "ok" if unit_path().exists() else "missing"))
    for name, status in checks:
        print(f"{name}: {status}")


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "init":
        _run_init(args.config, force=args.force)
        return
    if args.command == "run":
        asyncio.run(_run_daemon(args.config))
        return
    if args.command == "refresh":
        asyncio.run(_run_refresh(args.config, local=args.local))
        return
    if args.command == "status":
        asyncio.run(_run_status(args.json))
        return
    if args.command == "stats":
        _run_stats(args.json)
        return
    if args.command == "doctor":
        _run_doctor(args.config)
        return
    if args.command == "config":
        _run_config_command(args)
        return
    if args.command == "extension":
        _run_extension_command(args)
        return
    if args.command == "service":
        _run_service_command(args)
        return
    raise SystemExit(2)


if __name__ == "__main__":
    main()
