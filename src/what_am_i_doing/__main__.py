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
    build_minimal_config,
    default_config_path,
    LearnedRule,
    load_config,
    parse_target_from_hint,
    render_config,
    save_config,
    WindowExample,
)
from .constants import (
    CONFIG_DIR,
    CONFIG_PATH,
    DISCONNECTED_ICON,
    EXTENSION_DIR,
    EXTENSION_UUID,
    LEGACY_EXTENSION_UUIDS,
    SERVICE_NAME,
    UNCLASSIFIED_ICON,
)
from .daemon import ActivityDaemon
from .debug import follow_debug_entries, format_debug_entry, load_debug_entries
from .dbus_service import daemon_refresh_taxonomy, daemon_status_payload
from .models import AppPaths
from .resources import copy_resource_tree
from .service import install_unit, run_journalctl, run_systemctl, unit_path
from .storage import load_spans, load_status
from .timeline import TimelineApp
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

    learn_parser = subparsers.add_parser("learn")
    learn_parser.add_argument(
        "hint",
        help="Natural language hint with target path (e.g., 'opencode window should be coding/other')",
    )
    learn_parser.add_argument(
        "--skip-window", action="store_true", help="Skip window example selection"
    )

    subparsers.add_parser("run")
    refresh_parser = subparsers.add_parser("refresh")
    refresh_parser.add_argument(
        "--local", action="store_true", help="Refresh without D-Bus"
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

    timeline_parser = subparsers.add_parser("timeline")
    timeline_parser.add_argument(
        "--view",
        choices=["overview", "daily", "weekly", "stats"],
        default="daily",
        help="Starting view (default: daily)",
    )
    timeline_parser.add_argument(
        "--theme",
        default="green",
        help="Color theme (green, halloween, teal, blue, pink, purple, orange, monochrome, ylgnbu)",
    )

    subparsers.add_parser("doctor")

    debug_parser = subparsers.add_parser("debug")
    debug_sub = debug_parser.add_subparsers(dest="debug_command", required=True)
    debug_logs = debug_sub.add_parser("logs")
    debug_logs.add_argument("--lines", type=int, default=50)
    debug_logs.add_argument("--follow", action="store_true")
    debug_logs.add_argument("--json", action="store_true", help="Print raw JSON lines")

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

    return parser


async def _run_daemon(config_path: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    config = load_config(config_path)
    daemon = ActivityDaemon(config)
    await daemon.run()


async def _run_refresh(config_path: str, *, local: bool) -> None:
    if not local:
        try:
            success, message = await daemon_refresh_taxonomy()
            if success:
                print(f"taxonomy refreshed: {message}")
            else:
                print(f"warning: {message}")
            return
        except (DBusError, RuntimeError):
            pass
    config = load_config(config_path)
    daemon = ActivityDaemon(config)
    result = await daemon.refresh_taxonomy()
    if result.success:
        print(f"taxonomy refreshed: {result.message}")
    else:
        print(f"warning: {result.message}")


async def _run_status(json_output: bool) -> None:
    payload: dict[str, object]
    status = load_status(AppPaths.default().status_json)
    if status is not None:
        payload = {
            "kind": status.kind,
            "path": status.path,
            "top_level_id": status.top_level_id,
            "top_level_label": status.top_level_label,
            "icon_name": status.icon_name,
            "published_at": status.published_at.isoformat(),
            "taxonomy_hash": status.taxonomy_hash,
            "revision": status.revision,
            "source": "state-file",
        }
    else:
        try:
            payload = await daemon_status_payload()
            payload["source"] = "dbus"
        except (DBusError, RuntimeError, json.JSONDecodeError, ValueError):
            payload = {
                "kind": "disconnected",
                "path": None,
                "top_level_id": None,
                "top_level_label": None,
                "icon_name": DISCONNECTED_ICON,
                "published_at": None,
                "taxonomy_hash": None,
                "revision": 0,
                "source": "none",
            }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"kind: {payload['kind']}")
    print(f"path: {payload.get('path') or '-'}")
    print(f"top level: {payload.get('top_level_label') or '-'}")
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
    for span in spans:
        if window_start is not None and span.ended_at < window_start:
            continue
        by_top[span.top_level] = by_top.get(span.top_level, 0.0) + span.duration_seconds
        by_path[span.path] = by_path.get(span.path, 0.0) + span.duration_seconds
    return {"period": period, "by_top": by_top, "by_path": by_path}


def _run_stats(json_output: bool, period: str) -> None:
    payload = _stats_payload(period)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    by_top: dict[str, float] = payload["by_top"]
    by_path: dict[str, float] = payload["by_path"]

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


def _run_timeline(view: str, theme: str) -> None:
    spans = load_spans(AppPaths.default().spans_log)
    app = TimelineApp(spans=spans, start_view=view)
    if theme:
        app.theme_name = theme
    app.run()


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


def _run_doctor(config_path: str) -> None:
    checks: list[tuple[str, str]] = []
    path = Path(config_path).expanduser()
    checks.append(("config", "ok" if path.exists() else "missing"))
    try:
        config = load_config(path)
        checks.append(("config-parse", "ok"))
        for name, tool in {**config.tools.context, **config.tools.actions}.items():
            checks.append(
                (f"tool:{name}", "ok" if shutil.which(tool.run[0]) else "missing")
            )
    except Exception as exc:
        checks.append(("config-parse", f"error: {exc}"))
    checks.append(("gdbus", "ok" if shutil.which("gdbus") else "missing"))
    checks.append(
        ("gnome-extensions", "ok" if shutil.which("gnome-extensions") else "missing")
    )
    checks.append(("systemctl", "ok" if shutil.which("systemctl") else "missing"))
    checks.append(("extension", "ok" if EXTENSION_DIR.exists() else "missing"))
    checks.append(("service-unit", "ok" if unit_path().exists() else "missing"))
    for name, status in checks:
        print(f"{name}: {status}")


def _run_debug_command(args: argparse.Namespace) -> None:
    if args.debug_command != "logs":
        raise SystemExit(2)
    path = AppPaths.default().debug_log
    if args.follow:
        for entry in follow_debug_entries(path):
            _print_debug_entry(entry, json_output=args.json)
        return
    entries = load_debug_entries(path, lines=args.lines)
    if not entries:
        print(f"no debug logs yet at {path}")
        return
    for entry in entries:
        _print_debug_entry(entry, json_output=args.json)


def _print_debug_entry(entry: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(entry, sort_keys=True))
        return
    print(format_debug_entry(entry))


def _run_learn(config_path: str, hint: str, *, skip_window: bool) -> None:
    target = parse_target_from_hint(hint)
    window_example: WindowExample | None = None

    if not skip_window:
        paths = AppPaths.default()
        if paths.raw_events_log.exists():
            entries = load_raw_events_for_window_selection(paths.raw_events_log)
            if entries:
                print("Recent windows (select one to attach metadata, or skip):")
                for i, entry in enumerate(entries[:10], start=1):
                    title = entry.get("title", "")
                    wm_class = entry.get("wm_class", "")
                    workspace = entry.get("workspace_name", "") or entry.get(
                        "active_workspace_name", ""
                    )
                    print(f"  {i}. [{wm_class}] {title[:50]} ({workspace})")

                try:
                    selection = (
                        input("Select window (1-10) or 's' to skip: ").strip().lower()
                    )
                    if selection != "s" and selection.isdigit():
                        idx = int(selection) - 1
                        if 0 <= idx < len(entries[:10]):
                            selected = entries[idx]
                            window_example = WindowExample(
                                wm_class=selected.get("wm_class", ""),
                                title=selected.get("title", ""),
                                app_id=selected.get("app_id"),
                                workspace_name=selected.get("workspace_name")
                                or selected.get("active_workspace_name"),
                            )
                except (EOFError, KeyboardInterrupt):
                    print("\nskipped window selection")

    rule = LearnedRule(hint=hint, target=target, window_example=window_example)
    config = load_config(config_path)
    config.learned.append(rule)
    save_config(config_path, config)

    print(f"added learned rule: {hint}")
    print(f"  target: {target}")
    if window_example:
        print(f"  window: [{window_example.wm_class}] {window_example.title[:40]}")
    print(f"config updated: {Path(config_path).expanduser()}")
    print("run 'waid refresh' to regenerate taxonomy")


def load_raw_events_for_window_selection(path: Path) -> list[dict[str, Any]]:
    import json

    entries: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("event") == "window_change":
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
        entries.reverse()
        return entries
    except FileNotFoundError:
        return []


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "init":
        _run_init(args.config, force=args.force)
        return
    if args.command == "learn":
        _run_learn(args.config, args.hint, skip_window=args.skip_window)
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
    if args.command == "timeline":
        _run_timeline(args.view, args.theme)
        return
    if args.command == "doctor":
        _run_doctor(args.config)
        return
    if args.command == "debug":
        _run_debug_command(args)
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
