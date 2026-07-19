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


def _insert_capture(content: str, line: str) -> str:
    """Append `line` at the end of the '## Captures' section, creating the
    heading (at end of the note) if it is absent."""
    lines = content.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.strip() == CAPTURES_HEADING), None)
    if idx is None:
        base = content.rstrip("\n")
        sep = "\n\n" if base else ""
        return f"{base}{sep}{CAPTURES_HEADING}\n{line}\n"
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
    """Append `- YYYY-MM-DD HH:MM  text` under today's note's Captures heading,
    creating the note (with an H1 date header) and the heading if needed. Returns
    the note path. Raises FileNotFoundError if the vault folder does not exist."""
    cfg = cfg or load_config()
    now = now or datetime.now()
    vault: Path = cfg["vault"]
    if not vault.is_dir():
        raise FileNotFoundError(
            f"vault not found: {vault} — set it in ~/.desk/config.json")
    path = vault / cfg["daily_subdir"] / f"{now:%Y-%m-%d}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"- {now:%Y-%m-%d %H:%M}  {text.strip()}"
    content = path.read_text(encoding="utf-8") if path.exists() else f"# {now:%Y-%m-%d}\n"
    path.write_text(_insert_capture(content, line), encoding="utf-8")
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
