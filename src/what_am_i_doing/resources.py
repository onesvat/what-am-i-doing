from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def resource_text(*parts: str) -> str:
    resource = files("what_am_i_doing")
    for part in ("resources", *parts):
        resource = resource.joinpath(part)
    return resource.read_text(encoding="utf-8")


def copy_resource_tree(*parts: str, destination: Path) -> None:
    source = files("what_am_i_doing")
    for part in ("resources", *parts):
        source = source.joinpath(part)
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.is_file():
            destination.joinpath(item.name).write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
