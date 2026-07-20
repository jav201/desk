"""Capture panel — a rotating prompt nudges you to write; on enter the line is
appended to today's Obsidian daily note under a '## Captures' heading.

The vault location is read from ~/.desk/config.json
({"vault": "...", "daily_subdir": "Daily"}); the public default is ~/Obsidian,
so no personal path lives in the repo. Set your real vault in that config file.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.markup import escape as esc

CONFIG_PATH = Path.home() / ".desk" / "config.json"
DEFAULT_VAULT = Path.home() / "Obsidian"
DEFAULT_SUBDIR = "Daily"
FALLBACK_PATH = Path.home() / ".desk" / "captures.md"
CAPTURES_HEADING = "## Captures"

PROMPTS = [
    "What did you just figure out?",
    "What are you avoiding?",
    "A decision you made, and why?",
    "What's the next smallest step?",
    "What did that meeting change?",
    "An idea worth not losing?",
    "What's blocking you right now?",
    "Something you learned today?",
]


def load_config(path: Path | None = None) -> dict:
    path = path or CONFIG_PATH
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    return {
        "vault": Path(d.get("vault", str(DEFAULT_VAULT))),
        "daily_subdir": d.get("daily_subdir", DEFAULT_SUBDIR),
    }


def pick_prompt(i: int) -> str:
    return PROMPTS[i % len(PROMPTS)]


def _insert_under(content: str, heading: str, line: str) -> str:
    """Append `line` at the end of the given `heading`'s section, creating the
    heading (at the end of the file) if it is absent."""
    lines = content.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.strip() == heading), None)
    if idx is None:
        base = content.rstrip("\n")
        sep = "\n\n" if base else ""
        return f"{base}{sep}{heading}\n{line}\n"
    end = len(lines)
    for i in range(idx + 1, len(lines)):
        if lines[i].startswith("#"):
            end = i
            break
    while end - 1 > idx and lines[end - 1].strip() == "":
        end -= 1
    lines.insert(end, line)
    return "\n".join(lines) + "\n"


def append_capture(text: str, cfg: dict | None = None,
                   now: datetime | None = None) -> Path:
    """Append `- YYYY-MM-DD HH:MM  text` and return the file written.

    If the configured vault folder exists, write under a '## Captures' heading in
    <vault>/Daily/YYYY-MM-DD.md (creating the note + heading as needed). If the
    vault is NOT available (e.g. on a machine without it), fall back to a single
    local file ~/.desk/captures.md, grouped under a per-day '## YYYY-MM-DD'
    heading — so captures are never lost. Never raises for a missing vault.
    """
    cfg = cfg or load_config()
    now = now or datetime.now()
    line = f"- {now:%Y-%m-%d %H:%M}  {text.strip()}"
    vault: Path = cfg["vault"]
    if vault.is_dir():
        path = vault / cfg["daily_subdir"] / f"{now:%Y-%m-%d}.md"
        heading = CAPTURES_HEADING
        seed = f"# {now:%Y-%m-%d}\n"
    else:
        path = FALLBACK_PATH
        heading = f"## {now:%Y-%m-%d}"
        seed = "# desk captures\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.read_text(encoding="utf-8") if path.exists() else seed
    path.write_text(_insert_under(content, heading, line), encoding="utf-8")
    return path


def render_tile(prompt: str) -> str:
    return f"[dim]› {esc(prompt)}[/dim]"


def render_body(prompt: str, saved: str | None = None) -> str:
    out = ["[bold #2dd4bf]CAPTURE[/]", "",
           f"[#ffd166]{esc(prompt)}[/]",
           "[dim]type below · enter saves it to today's daily note[/dim]", ""]
    if saved:
        out.append(f"[#3fb950]✓ saved to {esc(saved)}[/]")
        out.append("")
    out.append("[dim]it also cycles through:[/dim]")
    for p in PROMPTS[1:4]:
        out.append(f"[dim]  · {esc(p)}[/dim]")
    return "\n".join(out)
