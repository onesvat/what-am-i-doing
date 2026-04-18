from __future__ import annotations

from .models import CatalogEntry


BUILTIN_ACTIVITY_DEFINITIONS: list[dict[str, str]] = [
    {
        "path": "browsing/social_media",
        "description": "Social feeds, community timelines, messaging apps used casually, and attention-grabbing scrolling.",
    },
    {
        "path": "browsing/shopping",
        "description": "Stores, product pages, carts, price comparisons, and purchase research.",
    },
    {
        "path": "browsing/llm",
        "description": "ChatGPT, Claude, Gemini, Perplexity, or other LLM tools used for prompting, drafting, or question answering.",
    },
    {
        "path": "browsing/research",
        "description": "Reference lookup, docs reading, articles, issue threads, and technical investigation not tied to a specific task.",
    },
    {
        "path": "browsing/news",
        "description": "News sites, newsletters, current events, and topical reading.",
    },
    {
        "path": "browsing/other",
        "description": "General web browsing that does not fit the more specific browsing categories.",
    },
    {
        "path": "coding/ide",
        "description": "Code editing, project navigation, refactoring, reading source, and other IDE-centered development.",
    },
    {
        "path": "coding/terminal",
        "description": "Shell-heavy work, git commands, builds, package management, servers, logs, and command-line development.",
    },
    {
        "path": "coding/review",
        "description": "Pull request review, diff inspection, and code reading focused on evaluating changes.",
    },
    {
        "path": "coding/debugging",
        "description": "Tracing bugs, reproducing failures, examining logs, and interactive troubleshooting.",
    },
    {
        "path": "communication/chat",
        "description": "Interactive chat conversations such as Slack, Telegram, Discord, or direct messaging for active discussion.",
    },
    {
        "path": "communication/email",
        "description": "Email reading, writing, triage, and inbox processing.",
    },
    {
        "path": "communication/meetings",
        "description": "Live meetings, calls, screen shares, and calendar-driven synchronous communication.",
    },
    {
        "path": "admin/planning",
        "description": "Planning, prioritization, todos, scheduling, and operational coordination.",
    },
    {
        "path": "admin/finance",
        "description": "Bills, banking, expense tracking, accounting, and financial admin.",
    },
    {
        "path": "writing/notes",
        "description": "Writing notes, drafting text, outlining, and maintaining documents outside a specific task.",
    },
    {
        "path": "learning/course",
        "description": "Structured learning, lessons, tutorials, studying, and practice.",
    },
    {
        "path": "media/video",
        "description": "Passive video consumption such as YouTube, streams, or recorded talks.",
    },
    {
        "path": "media/music",
        "description": "Passive audio listening, music, podcasts, or ambient media.",
    },
    {
        "path": "adult/explicit",
        "description": "Pornography, cam sites, hentai, explicit galleries, and clearly sexual adult content.",
    },
]


def builtin_activity_entries() -> list[CatalogEntry]:
    return [CatalogEntry.model_validate(item) for item in BUILTIN_ACTIVITY_DEFINITIONS]
