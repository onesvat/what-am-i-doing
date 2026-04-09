from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ColorLevel = Literal[0, 1, 2, 3, 4]


@dataclass(slots=True)
class ColorTheme:
    name: str
    levels: tuple[str, str, str, str, str]
    empty: str = "#161b22"
    background: str = "#0d1117"
    text: str = "#c9d1d9"
    accent: str = "#58a6ff"


THEMES: dict[str, ColorTheme] = {
    "green": ColorTheme(
        name="green",
        levels=("#9be9a8", "#40c463", "#30a14e", "#216e39", "#0e4429"),
        accent="#40c463",
    ),
    "halloween": ColorTheme(
        name="halloween",
        levels=("#ffe4c4", "#ffb347", "#ff8c00", "#ff6600", "#cc4400"),
        accent="#ff6600",
    ),
    "teal": ColorTheme(
        name="teal",
        levels=("#b2d8d8", "#66b2b2", "#008080", "#006666", "#004c4c"),
        accent="#008080",
    ),
    "blue": ColorTheme(
        name="blue",
        levels=("#c6e486", "#7bc96f", "#49af5d", "#2e8b57", "#196f3d"),
        empty="#1a1a2e",
        background="#0f0f1a",
        accent="#49af5d",
    ),
    "pink": ColorTheme(
        name="pink",
        levels=("#ffc0cb", "#ff69b4", "#ff1493", "#db7093", "#c71585"),
        accent="#ff69b4",
    ),
    "purple": ColorTheme(
        name="purple",
        levels=("#e6e6fa", "#b19cd9", "#9370db", "#8a2be2", "#6a0dad"),
        accent="#9370db",
    ),
    "orange": ColorTheme(
        name="orange",
        levels=("#ffe4b5", "#ffc87c", "#ffa500", "#ff8c00", "#cc5500"),
        accent="#ffa500",
    ),
    "monochrome": ColorTheme(
        name="monochrome",
        levels=("#e8e8e8", "#b8b8b8", "#888888", "#585858", "#282828"),
        empty="#1a1a1a",
        background="#0a0a0a",
        text="#888888",
        accent="#888888",
    ),
    "ylgnbu": ColorTheme(
        name="ylgnbu",
        levels=("#ffffd9", "#edf8b1", "#c7e9b4", "#7fcdbb", "#41b6c4"),
        accent="#7fcdbb",
    ),
}

THEME_NAMES = tuple(THEMES.keys())


def get_theme(name: str) -> ColorTheme:
    return THEMES.get(name, THEMES["green"])


def intensity_level(seconds: float, max_seconds: float) -> ColorLevel:
    if seconds == 0:
        return 0
    if max_seconds == 0:
        return 1
    ratio = seconds / max_seconds
    if ratio < 0.2:
        return 1
    if ratio < 0.4:
        return 2
    if ratio < 0.6:
        return 3
    if ratio < 0.8:
        return 4
    return 4


def level_color(theme: ColorTheme, level: ColorLevel) -> str:
    if level == 0:
        return theme.empty
    return theme.levels[level - 1]
