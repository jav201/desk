"""Board panel — reads the taskboard's board.json (read-only, loose coupling).

`desk` never imports the taskboard package; it parses ~/.taskboard/board.json and
tolerates it being missing, old, or half-written. Statuses are grouped into the
same three columns taskboard uses, and the legacy "active" name (boards written
before the doing-rename) is treated as doing.
"""
from __future__ import annotations

import json
from pathlib import Path

from rich.markup import escape as esc

BOARD_PATH = Path.home() / ".taskboard" / "board.json"

_TODO = ("backlog",)
_DOING = ("doing", "active", "blocked")     # "active" = legacy, pre-rename
_DONE = ("done",)
_PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}
_COLW = 18
_MAXROWS = 6


def load(path: Path | None = None) -> dict | None:
    """Parsed board.json, or None if missing/corrupt/half-written."""
    path = path or BOARD_PATH
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _projects(data: dict) -> dict:
    return {p.get("id"): p.get("name", "?") for p in data.get("projects", [])}


def _visible(data: dict) -> list:
    return [t for t in data.get("tasks", []) if not t.get("archived")]


def _proj_name(pid, projs) -> str:
    return projs.get(pid, "Inbox") if pid else "Inbox"


def current_doing(data: dict) -> dict | None:
    """The one task to show as 'now': first doing task, else first blocked."""
    tasks = _visible(data)
    doing = [t for t in tasks if t.get("status") in ("doing", "active")]
    if doing:
        return doing[0]
    blocked = [t for t in tasks if t.get("status") == "blocked"]
    return blocked[0] if blocked else None


def _cell(raw: str, cls: str | None = None, w: int = _COLW) -> str:
    raw = raw[:w]
    pad = " " * (w - len(raw))
    disp = esc(raw)
    return (f"[{cls}]{disp}[/]" if cls else disp) + pad


def render_tile(data: dict | None) -> str:
    if not data:
        return "› [dim](no board loaded)[/dim]"
    cur = current_doing(data)
    if not cur:
        return "› [dim](nothing in progress)[/dim]"
    proj = _proj_name(cur.get("project_id"), _projects(data))
    title = cur.get("title", "?")
    return f"[dim]›[/dim] [#ffd166]{esc(proj)} · {esc(title)}[/]"


def _sorted(tasks: list, statuses: tuple) -> list:
    ts = [t for t in tasks if t.get("status") in statuses]
    ts.sort(key=lambda t: _PRIORITY_RANK.get(t.get("priority"), 1))
    return ts


def _render_cell(colist: list, i: int, cur_id=None, done_col=False) -> str:
    if i >= len(colist):
        return _cell("")
    t = colist[i]
    title = t.get("title", "?")
    if cur_id and t.get("id") == cur_id:
        return _cell("▸ " + title, "#ffd166")
    if done_col:
        return _cell("✓ " + title, "#3fb950")
    if t.get("priority") == "high":
        return _cell("! " + title, "#ff8c42")
    return _cell("  " + title)


def render_body(data: dict | None) -> str:
    if not data:
        return ("[bold #2dd4bf]BOARD[/]\n\n"
                "[dim]no board at ~/.taskboard/board.json[/dim]\n"
                "[dim]install and run taskboard to populate this.[/dim]")
    projs = _projects(data)
    tasks = _visible(data)
    todo = _sorted(tasks, _TODO)
    doing = _sorted(tasks, _DOING)
    done = _sorted(tasks, _DONE)
    cur = current_doing(data)
    cur_id = cur.get("id") if cur else None
    out = ["[bold #2dd4bf]BOARD[/]", ""]
    out.append(_cell(f"TODO {len(todo)}", "bold")
               + _cell(f"DOING {len(doing)}", "bold")
               + _cell(f"DONE {len(done)}", "bold"))
    rows = min(max(len(todo), len(doing), len(done), 1), _MAXROWS)
    for i in range(rows):
        out.append(_render_cell(todo, i)
                   + _render_cell(doing, i, cur_id=cur_id)
                   + _render_cell(done, i, done_col=True))
    if max(len(todo), len(doing), len(done)) > _MAXROWS:
        out.append("[dim]… more in taskboard[/dim]")
    if cur:
        out.append("")
        out.append(f"[dim]now[/dim] [#ffd166]▸ {esc(_proj_name(cur.get('project_id'), projs))}"
                   f" · {esc(cur.get('title', '?'))}[/]")
    return "\n".join(out)
