from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CategoryDefinition:
    name: str
    icon: str
    description: str
    subcategories: list[str] | None = None
    subcategory_selectable: bool = False


CATEGORY_CATALOG: list[CategoryDefinition] = [
    CategoryDefinition(
        name="coding",
        icon="laptop-symbolic",
        description="Software development: coding, debugging, IDEs, terminals, Git, tests, build tools, and technical browser work that directly supports active development.",
    ),
    CategoryDefinition(
        name="writing",
        icon="document-edit-symbolic",
        description="Writing and editing substantial text: docs, notes, reports, thesis drafts, blog posts, and other long-form content.",
    ),
    CategoryDefinition(
        name="learning",
        icon="book-open-symbolic",
        description="Intentional learning: courses, study sessions, tutorials, papers, educational videos, and reading to build understanding.",
    ),
    CategoryDefinition(
        name="communication",
        icon="mail-unread-symbolic",
        description="Communication work: email, chat, and meetings.",
        subcategories=["email", "chat", "meeting"],
        subcategory_selectable=True,
    ),
    CategoryDefinition(
        name="admin",
        icon="system-file-manager-symbolic",
        description="Routine operations: task management, calendar, planning, finance, forms, and personal or work admin.",
    ),
    CategoryDefinition(
        name="browsing",
        icon="web-browser-symbolic",
        description="General web browsing that is not active development or structured learning. Includes social media, shopping, news, casual entertainment, and generic reference lookups.",
        subcategories=[
            "social_media",
            "shopping",
            "news",
            "entertainment",
            "reference",
        ],
        subcategory_selectable=False,
    ),
    CategoryDefinition(
        name="media",
        icon="multimedia-player-symbolic",
        description="Passive media consumption and entertainment through video or audio.",
        subcategories=["video", "audio"],
        subcategory_selectable=True,
    ),
    CategoryDefinition(
        name="gaming",
        icon="gamepad-symbolic",
        description="Playing games: Steam, browser games, emulators, or console.",
    ),
    CategoryDefinition(
        name="adult",
        icon="dialog-warning-symbolic",
        description="Explicit sexual content and NSFW material.",
    ),
]


def get_category_definition(name: str) -> CategoryDefinition | None:
    for cat in CATEGORY_CATALOG:
        if cat.name == name:
            return cat
    return None


def get_icon_for_path(path: str) -> str:
    top, _, child = path.partition("/")
    cat = get_category_definition(top)
    if cat is None:
        return "applications-system-symbolic"
    return cat.icon


def get_description_for_path(path: str) -> str:
    top, _, child = path.partition("/")
    cat = get_category_definition(top)
    if cat is None:
        return f"Broad {path} activity."
    if child and cat.subcategories:
        child_desc = _subcategory_description(top, child)
        if child_desc:
            return child_desc
    return cat.description


def _subcategory_description(parent: str, child: str) -> str | None:
    descriptions = {
        (
            "communication",
            "email",
        ): "Email communication: Gmail, Outlook, and other email clients.",
        (
            "communication",
            "chat",
        ): "Chat communication: Slack, Discord, Telegram, Teams chat, and similar messaging.",
        (
            "communication",
            "meeting",
        ): "Meetings and calls: Zoom, Teams, Google Meet, presentations, and live collaboration.",
        (
            "browsing",
            "social_media",
        ): "Social media browsing: Twitter, Facebook, Reddit, Instagram, and similar feeds.",
        (
            "browsing",
            "shopping",
        ): "Shopping and product browsing: Amazon, e-commerce sites, and price comparison.",
        ("browsing", "news"): "News browsing: news sites, RSS feeds, and current events.",
        (
            "browsing",
            "entertainment",
        ): "Casual entertainment browsing: humor sites, memes, celebrity content, and fun links.",
        (
            "browsing",
            "reference",
        ): "Generic reference lookup: Wikipedia, dictionaries, quick factual checks, and non-project reading.",
        ("media", "video"): "Video entertainment and passive watching: YouTube, Netflix, streaming platforms, and similar playback.",
        ("media", "audio"): "Audio entertainment and passive listening: Spotify, podcasts, music players, and similar playback.",
    }
    return descriptions.get((parent, child))


def resolve_category_paths(paths: list[str]) -> list[str]:
    """Expand top-level paths to include all default subcategories if applicable.

    Custom categories not in catalog are still included (not skipped).
    """
    result: list[str] = []
    for path in paths:
        top, _, child = path.partition("/")
        cat = get_category_definition(top)

        if cat is None:
            result.append(path)
            continue

        if child:
            result.append(path)
            continue

        if cat.subcategories and not cat.subcategory_selectable:
            for sub in cat.subcategories:
                result.append(f"{top}/{sub}")
        else:
            result.append(top)

    return result


def validate_category_path(path: str) -> bool:
    """Check if a category path exists in the catalog."""
    top, _, child = path.partition("/")
    cat = get_category_definition(top)
    if cat is None:
        return False
    if not child:
        return True
    if cat.subcategories and child in cat.subcategories:
        return True
    return False


def catalog_as_choices() -> list[tuple[str, str]]:
    """Return catalog as list of (name, default_note) for wizard compatibility."""
    return [(cat.name, cat.description[:50]) for cat in CATEGORY_CATALOG]
