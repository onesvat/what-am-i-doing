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
        description="Development: writing code, debugging, IDEs, terminals, Git, tests.",
    ),
    CategoryDefinition(
        name="research",
        icon="book-open-symbolic",
        description="Purposeful reading: docs, papers, tutorials, Stack Overflow, learning.",
    ),
    CategoryDefinition(
        name="writing",
        icon="document-edit-symbolic",
        description="Creating text: documents, notes, blog posts, emails (composing), journaling.",
    ),
    CategoryDefinition(
        name="communication",
        icon="mail-unread-symbolic",
        description="Communication. Email (Gmail, Outlook), chat (Slack, Discord, Telegram), meeting (Zoom, Teams, video calls).",
        subcategories=["email", "chat", "meeting"],
        subcategory_selectable=True,
    ),
    CategoryDefinition(
        name="admin",
        icon="system-file-manager-symbolic",
        description="Personal admin. Finance (banking, bills, taxes), personal (forms, appointments, documents).",
        subcategories=["finance", "personal"],
        subcategory_selectable=True,
    ),
    CategoryDefinition(
        name="media",
        icon="multimedia-player-symbolic",
        description="Entertainment. Video (YouTube, Netflix, streaming), audio (Spotify, podcasts, music).",
        subcategories=["video", "audio"],
        subcategory_selectable=True,
    ),
    CategoryDefinition(
        name="gaming",
        icon="gamepad-symbolic",
        description="Playing games: Steam, browser games, emulators, console.",
    ),
    CategoryDefinition(
        name="browsing",
        icon="web-browser-symbolic",
        description="Web browsing. Social media (Twitter, Facebook, Reddit, Instagram), shopping (Amazon, e-commerce), news (news sites, RSS), entertainment (humor, memes), reference (Wikipedia, dictionaries).",
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
        name="adult",
        icon="dialog-warning-symbolic",
        description="Adult content: porn sites, adult entertainment. Private.",
    ),
    CategoryDefinition(
        name="break",
        icon="coffee-cup-symbolic",
        description="Intentional pauses: coffee, snacks, stepping away.",
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
        ): "Email communication: Gmail, Outlook, email clients.",
        (
            "communication",
            "chat",
        ): "Chat messaging: Slack, Discord, Telegram, Teams chat.",
        (
            "communication",
            "meeting",
        ): "Video meetings: Zoom, Teams, Google Meet, presentations.",
        ("admin", "finance"): "Financial admin: banking, bills, taxes, investments.",
        ("admin", "personal"): "Personal admin: forms, appointments, documents.",
        ("media", "video"): "Video content: YouTube, Netflix, streaming platforms.",
        ("media", "audio"): "Audio content: Spotify, podcasts, music players.",
        (
            "browsing",
            "social_media",
        ): "Social media: Twitter, Facebook, Reddit, Instagram.",
        (
            "browsing",
            "shopping",
        ): "Shopping: Amazon, e-commerce sites, price comparison.",
        ("browsing", "news"): "News browsing: news sites, RSS feeds, current events.",
        (
            "browsing",
            "entertainment",
        ): "Entertainment browsing: humor sites, memes, fun content.",
        (
            "browsing",
            "reference",
        ): "Reference lookup: Wikipedia, dictionaries, quick info.",
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
