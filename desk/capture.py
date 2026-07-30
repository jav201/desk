"""Capture panel — a rotating prompt nudges you to write; on enter the line is
appended to today's Obsidian daily note under a '## Captures' heading.

The vault location is read from ~/.desk/config.json
({"vault": "...", "daily_subdir": "Daily"}); the public default is ~/Obsidian,
so no personal path lives in the repo. Set your real vault in that config file.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from rich.cells import cell_len
from rich.markup import escape as esc

from . import deck

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


# ---- the card seat (the deck's M/L form) ------------------------------------
_TAG = re.compile(r"(?<!\\)\[/?[^\]]*\]")


def _vis(markup: str) -> int:
    """Cells the markup occupies once painted — see `focus._vis`."""
    return cell_len(_TAG.sub("", markup).replace("\\[", "["))


def _pick(cands, w: int) -> str:
    for c in cands:
        if _vis(c) <= w:
            return c
    return ""


def _clip(text: str, n: int) -> str:
    """Clip PLAIN text to `n` cells, before it is escaped and wrapped — clipping
    afterwards would cut a markup tag in half or split an escape from its
    bracket."""
    if n <= 0:
        return ""
    if cell_len(text) <= n:
        return text
    out = ""
    for ch in text:
        if cell_len(out + ch) > n - 1:
            break
        out += ch
    return out + "…"


def _cycle(prompt: str, n: int) -> list:
    """The prompts after this one, wrapping — the rotation the capture box walks
    on every enter, shown a few ahead."""
    try:
        i = PROMPTS.index(prompt) + 1
    except ValueError:
        i = 0
    return [PROMPTS[(i + k) % len(PROMPTS)] for k in range(min(n, len(PROMPTS) - 1))]


def card_fields(prompt: str, saved: str | None, w: int, h: int, want: int,
                head: str = "[bold #2dd4bf]CAPTURE[/]"):
    """[(declared field, [line, ...]), ...] — the first `want` fields of the
    capture card, in `deck.CARD_FIELDS` order."""
    out = []
    for idx, name in enumerate(deck.CARD_FIELDS["capture"][:want]):
        if name == "head":
            out.append((name, [head]))
        elif name == "prompt":
            out.append((name, [f"  [#ffd166]{esc(_clip(prompt, w - 2))}[/]"]))
        elif name == "input":
            out.append((name, [
                _pick(["  [dim]c opens the capture box[/dim]",
                       "  [dim]c captures[/dim]"], w),
                _pick(["  [dim]enter saves it to today's note[/dim]",
                       "  [dim]enter saves the line[/dim]",
                       "  [dim]enter saves[/dim]"], w)]))
        elif name == "cycle":
            rows = deck.room(h, "capture", idx, want)
            out.append((name, [f"  [dim]· {esc(_clip(p, w - 4))}[/dim]"
                               for p in _cycle(prompt, rows)]))
        else:
            out.append((name, [
                f"  [#3fb950]✓ saved to {esc(_clip(saved, w - 13))}[/]" if saved
                else _pick(["  [dim]→ today's daily note[/dim]",
                            "  [dim]→ daily note[/dim]"], w)]))
    return out


def render_card(prompt: str, saved: str | None, w: int, h: int, want: int,
                head: str = "[bold #2dd4bf]CAPTURE[/]") -> str:
    return "\n".join(l for _n, ls in card_fields(prompt, saved, w, h, want, head)
                     for l in ls)
