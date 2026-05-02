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
        "description": "Reference lookup, docs reading, articles, issue threads, and general research that is not clearly a task match.",
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
        "description": "Code editing in a graphical IDE or editor: VS Code, JetBrains IDEs, Zed, Sublime, Xcode, Android Studio, GNOME Builder, OpenCode (title starts with 'OC'). Also choose this when a TUI editor (nvim, vim, emacs, helix) is clearly active inside a terminal (title shows filename with editor markers like [n], INSERT, or editor-specific patterns). Do NOT choose this for shell prompts showing directory paths (~/Code/project, ~/Projects/repo) — those are terminals.",
    },
    {
        "path": "coding/terminal",
        "description": "Any terminal emulator (kitty, alacritty, wezterm, foot, gnome-terminal, konsole, xterm, tmux, ghostty) when it is NOT running a TUI editor. Shell prompts showing directories (~/Code/project, ~/foo/bar), git commands, builds, package managers, REPLs, servers, logs, SSH sessions, Claude Code, LLM CLIs, OpenCode CLI sessions (title contains 'dialogus'). Default coding choice for wm_class of a terminal emulator unless a TUI editor is visibly active.",
    },
    {
        "path": "communication/chat",
        "description": "Active chat conversations, direct messages, team messaging, and text-based back-and-forth communication.",
    },
    {
        "path": "communication/email",
        "description": "Reading, writing, triaging, and processing email.",
    },
    {
        "path": "communication/meetings",
        "description": "Live meetings, calls, video conferences, screen shares, and synchronous discussion.",
    },
    {
        "path": "communication/other",
        "description": "Communication work that does not fit chat, email, or meetings.",
    },
    {
        "path": "admin",
        "description": "Planning, scheduling, todos, finance, operational chores, and general administrative work.",
    },
    {
        "path": "writing",
        "description": "Writing, drafting, note-taking, outlining, and maintaining text outside a specific task match.",
    },
    {
        "path": "learning",
        "description": "Studying, tutorials, lessons, guided learning, and practice where the main goal is learning.",
    },
    {
        "path": "media/video",
        "description": "Passive video consumption such as YouTube, streams, recorded talks, or shows.",
    },
    {
        "path": "media/audio",
        "description": "Passive audio consumption such as music, podcasts, radio, or ambient listening.",
    },
    {
        "path": "media/other",
        "description": "Passive media consumption that does not fit video or audio clearly.",
    },
    {
        "path": "system",
        "description": "Local file management, settings, installers, updates, and general machine or desktop maintenance.",
    },
    {
        "path": "gaming",
        "description": "Games, emulators, launchers, and active gameplay.",
    },
    {
        "path": "adult",
        "description": "Pornography, cam sites, hentai, explicit galleries, and clearly sexual adult content.",
    },
]


def builtin_activity_entries() -> list[CatalogEntry]:
    return [CatalogEntry.model_validate(item) for item in BUILTIN_ACTIVITY_DEFINITIONS]
