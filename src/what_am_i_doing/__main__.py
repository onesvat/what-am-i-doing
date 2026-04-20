from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from dbus_next.errors import DBusError

from .config import (
    build_selection_catalog,
    build_minimal_config,
    default_config_path,
    default_tasks_path,
    load_config,
    load_tasks,
    render_config,
)
from .constants import (
    DISCONNECTED_ICON,
    EXTENSION_DIR,
    EXTENSION_UUID,
    LEGACY_EXTENSION_UUIDS,
    SERVICE_NAME,
)
from .daemon import ActivityDaemon
from .dbus_service import (
    daemon_get_tracking,
    daemon_reload_config,
    daemon_set_tracking,
    daemon_ui_state_payload,
)
from .models import AppPaths
from .resources import copy_resource_tree
from .service import install_unit, run_journalctl, run_systemctl, unit_path
from .storage import load_spans, load_status, load_ui_state
from .wizard import run_init_wizard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="waid")
    parser.add_argument(
        "--config", default=str(default_config_path()), help="Path to config file"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing config"
    )

    subparsers.add_parser("run")
    refresh_parser = subparsers.add_parser("refresh")
    refresh_parser.add_argument(
        "--local", action="store_true", help="Reload config without D-Bus"
    )

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON"
    )

    stats_parser = subparsers.add_parser("stats")
    stats_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON"
    )
    stats_parser.add_argument(
        "--period",
        choices=["today", "week", "month", "all"],
        default="today",
        help="Time period to show (default: today)",
    )

    config_parser = subparsers.add_parser("config")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("path")
    config_sub.add_parser("edit")
    config_sub.add_parser("validate")

    extension_parser = subparsers.add_parser("extension")
    extension_sub = extension_parser.add_subparsers(
        dest="extension_command", required=True
    )
    extension_sub.add_parser("install")
    extension_sub.add_parser("status")

    service_parser = subparsers.add_parser("service")
    service_sub = service_parser.add_subparsers(dest="service_command", required=True)
    install = service_sub.add_parser("install")
    install.add_argument(
        "--now", action="store_true", help="Enable and start after install"
    )
    service_sub.add_parser("uninstall")
    service_sub.add_parser("start")
    service_sub.add_parser("stop")
    service_sub.add_parser("restart")
    service_sub.add_parser("status")
    logs = service_sub.add_parser("logs")
    logs.add_argument("--lines", type=int, default=100)
    logs.add_argument("--follow", action="store_true")

    tracking_parser = subparsers.add_parser("tracking")
    tracking_sub = tracking_parser.add_subparsers(
        dest="tracking_command", required=True
    )
    tracking_sub.add_parser("status")
    tracking_sub.add_parser("pause")
    tracking_sub.add_parser("resume")

    return parser


async def _run_daemon(config_path: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    resolved = Path(config_path).expanduser()
    config = load_config(resolved)
    daemon = ActivityDaemon(config, config_path=resolved)
    await daemon.run()


async def _run_refresh(config_path: str, *, local: bool) -> None:
    if not local:
        try:
            success, message = await daemon_reload_config()
            if success:
                print(f"catalog reloaded: {message}")
            else:
                print(f"warning: {message}")
            return
        except (DBusError, RuntimeError):
            pass
    resolved = Path(config_path).expanduser()
    config = load_config(resolved)
    daemon = ActivityDaemon(config, config_path=resolved)
    result = await daemon.reload_config()
    if result.success:
        print(f"catalog reloaded: {result.message}")
    else:
        print(f"warning: {result.message}")


async def _run_status(json_output: bool) -> None:
    payload: dict[str, object]
    ui_state = load_ui_state(AppPaths.default().status_json)
    if ui_state is not None:
        payload = {
            **ui_state.model_dump(mode="json"),
            "source": "state-file",
        }
    else:
        try:
            payload = await daemon_ui_state_payload()
            payload["source"] = "dbus"
        except (DBusError, RuntimeError, json.JSONDecodeError, ValueError):
            payload = {
                "kind": "disconnected",
                "path": None,
                "task_path": None,
                "top_level_id": None,
                "top_level_label": None,
                "icon_name": DISCONNECTED_ICON,
                "published_at": None,
                "catalog_hash": None,
                "tracking_enabled": True,
                "display_label": "disconnected",
                "display_rows": [],
                "revision": 0,
                "source": "none",
            }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"kind: {payload['kind']}")
    print(f"path: {payload.get('path') or '-'}")
    print(f"task: {payload.get('task_path') or '-'}")
    print(f"label: {payload.get('display_label') or '-'}")
    print(f"icon: {payload['icon_name']}")
    if payload.get("published_at"):
        print(f"updated: {payload['published_at']}")
    print(f"revision: {payload.get('revision', 0)}")
    print(f"source: {payload['source']}")


def _format_duration(seconds: float) -> str:
    total_minutes = round(seconds / 60)
    if total_minutes < 1:
        return "<1m"
    hours, minutes = divmod(total_minutes, 60)
    if hours == 0:
        return f"{minutes}m"
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes}m"


def _stats_payload(period: str) -> dict[str, Any]:
    spans = load_spans(AppPaths.default().spans_log)
    now = datetime.now(tz=UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = {
        "today": day_start,
        "week": day_start - timedelta(days=day_start.weekday()),
        "month": day_start.replace(day=1),
        "all": None,
    }[period]

    by_top: dict[str, float] = {}
    by_path: dict[str, float] = {}
    by_task: dict[str, float] = {}
    for span in spans:
        if window_start is not None and span.started_at < window_start:
            continue
        by_top[span.top_level] = by_top.get(span.top_level, 0.0) + span.duration_seconds
        by_path[span.path] = by_path.get(span.path, 0.0) + span.duration_seconds
        if span.task_path:
            by_task[span.task_path] = by_task.get(span.task_path, 0.0) + span.duration_seconds
    return {"period": period, "by_top": by_top, "by_path": by_path, "by_task": by_task}


def _run_stats(json_output: bool, period: str) -> None:
    payload = _stats_payload(period)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    by_top: dict[str, float] = payload["by_top"]
    by_path: dict[str, float] = payload["by_path"]
    by_task: dict[str, float] = payload["by_task"]

    period_label = {
        "today": "Today",
        "week": "This week",
        "month": "This month",
        "all": "All time",
    }[period]
    print(period_label)

    total = sum(by_top.values())
    col_width = 32
    sorted_tops = sorted(by_top.items(), key=lambda x: x[1], reverse=True)
    for top, top_secs in sorted_tops:
        dur = _format_duration(top_secs)
        print(f"  {top:<{col_width - 2}}{dur:>6}")
        subs = [
            (p, s) for p, s in by_path.items() if p != top and p.startswith(top + "/")
        ]
        for path, secs in sorted(subs, key=lambda x: x[1], reverse=True):
            label = f"  {path}"
            dur = _format_duration(secs)
            print(f"  {label:<{col_width - 2}}{dur:>6}")

    print(f"  {'─' * (col_width + 4)}")
    print(f"  {'Total':<{col_width - 2}}{_format_duration(total):>6}")
    if by_task:
        print("\nSP Tasks")
        for task, secs in sorted(by_task.items(), key=lambda x: x[1], reverse=True):
            print(f"  {task:<{col_width - 2}}{_format_duration(secs):>6}")


def _initial_config_comments() -> str:
    return (
        "\n"
        "# Built-in activities live in waid itself.\n"
        "# Use allow_activities/block_activities to filter them.\n"
        "# Example custom activities:\n"
        "# activities:\n"
        "#   - path: custom/project-a\n"
        "#     description: Active custom activity\n"
        "#     icon: laptop-symbolic\n"
        "#\n"
        "# Tasks live in a separate file.\n"
        f"# Edit {default_tasks_path()} to add generated or hand-written tasks.\n"
        "#\n"
        "# Example action tool:\n"
        "# tools:\n"
        "#   actions:\n"
        "#     sp_start:\n"
        "#       run: [\"sp\", \"task\", \"start\"]\n"
    )


def _run_init(config_path: str, *, force: bool) -> None:
    path = Path(config_path).expanduser()
    if path.exists() and not force:
        raise SystemExit(f"config already exists at {path}; use --force to overwrite")
    answers = run_init_wizard()
    config = build_minimal_config(
        base_url=answers.base_url,
        model_name=answers.model_name,
        api_key_env=answers.api_key_env,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    AppPaths.default().state_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(render_config(config) + _initial_config_comments(), encoding="utf-8")
    print(f"wrote config: {path}")
    print("next:")
    print("  waid config edit")
    print("  waid extension install")
    print(f"  gnome-extensions enable {EXTENSION_UUID}")
    print("  waid service install --now")


def _run_config_command(args: argparse.Namespace) -> None:
    path = Path(args.config).expanduser()
    if args.config_command == "path":
        print(path)
        return
    if args.config_command == "validate":
        config = load_config(path)
        build_selection_catalog(config, load_tasks())
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
        for legacy_uuid in LEGACY_EXTENSION_UUIDS:
            legacy_dir = EXTENSION_DIR.parent / legacy_uuid
            if legacy_dir.exists():
                shutil.rmtree(legacy_dir)
        copy_resource_tree("gnome", destination=EXTENSION_DIR)
        print(f"installed extension to {EXTENSION_DIR}")
        print(f"enable with: gnome-extensions enable {EXTENSION_UUID}")
        print(
            "if GNOME says the extension does not exist yet, log out and back in first, then run the enable command again"
        )
        print(
            "if GNOME marks the extension as out of date after an upgrade, log out and back in so Shell reloads the new metadata"
        )
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
            proc = run_systemctl("enable", "--now", SERVICE_NAME)
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
                [
                    "journalctl",
                    "--user",
                    "-u",
                    SERVICE_NAME,
                    "-n",
                    str(args.lines),
                    "-f",
                ],
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


async def _run_tracking_command(args: argparse.Namespace) -> None:
    if args.tracking_command == "status":
        try:
            enabled = await daemon_get_tracking()
            print("enabled" if enabled else "paused")
        except (DBusError, RuntimeError):
            status = load_status(AppPaths.default().status_json)
            if status is not None and status.kind == "paused":
                print("paused")
            else:
                print("enabled (daemon not reachable, assuming enabled)")
        return
    if args.tracking_command == "pause":
        try:
            await daemon_set_tracking(False)
            print("tracking paused")
        except (DBusError, RuntimeError):
            raise SystemExit("daemon not reachable")
        return
    if args.tracking_command == "resume":
        try:
            await daemon_set_tracking(True)
            print("tracking resumed")
        except (DBusError, RuntimeError):
            raise SystemExit("daemon not reachable")
        return
    raise SystemExit(2)


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
        _run_stats(args.json, args.period)
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
    if args.command == "tracking":
        asyncio.run(_run_tracking_command(args))
        return
    raise SystemExit(2)


if __name__ == "__main__":
    main()
