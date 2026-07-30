"""Board panel — reads the taskboard's board.json (read-only, loose coupling).

desk never imports the taskboard package; it parses ~/.taskboard/board.json and
tolerates it being missing, old, or half-written. Every task is passed through a
normalisation/rescue layer (`normalize`) that understands BOTH the current
phase-based schema and the legacy status schema, and never silently drops a task
whose format has drifted — a task with a missing title keeps a placeholder, a
task with no phase lands in the first column, so a schema change can never lose
work off the board. The panel renders "mission control": a hero NOW banner, a
14-day due horizon, and a per-project progress ledger.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from rich.markup import escape as esc

from . import deck

BOARD_PATH = Path.home() / ".taskboard" / "board.json"

DEFAULT_PHASES = ("Backlog", "Doing", "Done")
# legacy task.status -> (phase name, blocked); kept forever so boards written
# before the phase migration still load with their tasks in the right column.
_LEGACY_STATUS = {
    "backlog": ("Backlog", False),
    "active": ("Doing", False),     # pre-rename name for "doing"
    "doing": ("Doing", False),
    "blocked": ("Doing", True),
    "done": ("Done", False),
}
_PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}

# project colour names (taskboard's palette) -> hex, so desk paints each project
# the same colour taskboard does without importing it.
_COLOR_HEX = {
    "rose": "#fb7185", "orange": "#fb923c", "amber": "#fbbf24", "lime": "#a3e635",
    "green": "#4ade80", "cyan": "#22d3ee", "sky": "#38bdf8", "blue": "#60a5fa",
    "indigo": "#818cf8", "violet": "#a78bfa", "fuchsia": "#e879f9", "pink": "#f472b6",
}
_MUTED = "#6b7787"          # Inbox / unknown project / drained bar
_TEAL = "#2dd4bf"           # header + today rule
_GOLD = "#ffd166"          # the now-task / doing chip
# THE HUE RATION. Project hues NAME ("whose is this?"); severity hues JUDGE
# ("how bad is this?"); no mark wears both. Severity gets exactly ONE reserved
# hue and overdue keeps it — a date that has passed is the only thing desk
# judges. High priority used to hold a second one (#ff8c42) and gave it up: it
# is drawn as `!2`, a mark and a count, which is the GLYPH house it already
# lived in, and the orange was the redundant half of that signal. It was also
# 9 rgb units from taskboard's `orange` project colour, so an orange project's
# bar and a priority chip were the same colour on the same row.
_OVER = "#f43f5e"           # overdue — the ONE reserved severity hue
_DIM = "#5b6675"           # horizon empty cells

BODY_W = 60                 # target render width (flexible #stage; art is exact)
_BAR = 8                    # ledger progress-bar cells
_NAMEW = 18                 # ledger project-name column
_HORIZON = 14               # days shown on the due horizon


# ---- IO ---------------------------------------------------------------------
def load(path: Path | None = None) -> dict | None:
    """Parsed board.json, or None if missing/corrupt/half-written."""
    path = path or BOARD_PATH
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _phases(data: dict) -> tuple:
    ph = data.get("phases")
    if isinstance(ph, list) and all(isinstance(p, str) and p.strip() for p in ph) and ph:
        return tuple(p.strip() for p in ph)
    return DEFAULT_PHASES


def _match_phase(name: str, phases: tuple) -> str:
    """Map a raw phase name onto an actual board phase (case-insensitive), or
    keep the raw string if the board has no such phase (a custom/unknown phase
    is preserved, not discarded)."""
    for p in phases:
        if p.lower() == name.strip().lower():
            return p
    return name.strip()


def _parse_due(raw: dict):
    v = raw.get("due_date") or raw.get("due")
    if not isinstance(v, str):
        return None
    try:
        return datetime.strptime(v[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def normalize(data: dict, phases: tuple | None = None) -> tuple[list, tuple, dict]:
    """Turn raw board.json tasks into canonical task dicts, rescuing drift.

    Returns (tasks, phases, report). Each task has: id, title, phase, blocked,
    priority, project_id, due (date|None), archived, rescued (bool), issues.
    A task is only skipped if its entry is not an object at all; everything else
    is repaired and kept, so no work disappears when the schema changes.
    """
    phases = phases or _phases(data)
    tasks: list = []
    report = {"total": 0, "rescued": 0, "dropped": 0, "issues": []}
    for raw in data.get("tasks", []) or []:
        report["total"] += 1
        if not isinstance(raw, dict):
            report["dropped"] += 1
            report["issues"].append("non-object task entry skipped")
            continue
        issues: list[str] = []

        title = raw.get("title")
        if not isinstance(title, str) or not title.strip():
            title = "(untitled)"
            issues.append("missing/blank title -> placeholder")
        else:
            title = title.strip()

        ph_raw = raw.get("phase")
        blocked = bool(raw.get("blocked", False))
        if isinstance(ph_raw, str) and ph_raw.strip():
            phase = _match_phase(ph_raw, phases)
        else:
            st = raw.get("status")
            key = st.strip().lower() if isinstance(st, str) else None
            if key in _LEGACY_STATUS:
                name, blk = _LEGACY_STATUS[key]
                phase = _match_phase(name, phases)
                blocked = blocked or blk
            else:
                phase = phases[0]                       # rescue: default column
                issues.append("no phase/status -> first column")

        pr = raw.get("priority")
        if pr not in _PRIORITY_RANK:
            pr = "normal"

        rescued = bool(issues)
        if rescued:
            report["rescued"] += 1
            report["issues"].extend(issues)
        tasks.append({
            "id": raw.get("id"),
            "title": title,
            "phase": phase,
            "blocked": blocked,
            "priority": pr,
            "project_id": raw.get("project_id"),
            "due": _parse_due(raw),
            "archived": bool(raw.get("archived", False)),
            "rescued": rescued,
            "issues": issues,
        })
    return tasks, phases, report


def validate(data: dict | None) -> dict:
    """A quick health report for a board without rendering it — how many tasks
    loaded, how many needed rescue, and why. Useful to spot schema drift early."""
    if not isinstance(data, dict):
        return {"total": 0, "rescued": 0, "dropped": 0,
                "issues": ["board.json missing or not an object"]}
    _, _, report = normalize(data)
    return report


# ---- derived views ----------------------------------------------------------
def _projects(data: dict) -> dict:
    out = {}
    for p in data.get("projects", []) or []:
        if isinstance(p, dict):
            out[p.get("id")] = (p.get("name", "?"), _COLOR_HEX.get(p.get("color"), _MUTED))
    return out


def _proj(pid, projs) -> tuple[str, str]:
    if pid and pid in projs:
        return projs[pid]
    return ("Inbox", _MUTED)


def _buckets(tasks: list, phases: tuple) -> tuple[list, list, list]:
    """Split non-archived tasks into (todo, doing, done) columns by phase:
    first phase = todo, last phase = done, anything else = doing."""
    first, last = phases[0], phases[-1]
    vis = [t for t in tasks if not t["archived"]]
    todo = [t for t in vis if t["phase"] == first]
    done = [t for t in vis if t["phase"] == last and last != first]
    doing = [t for t in vis if t["phase"] != first and t["phase"] != last]
    return todo, doing, done


def current_doing(data: dict) -> dict | None:
    """The one task to show as 'now': first unblocked doing task, else first
    blocked one, else None."""
    if not data:
        return None
    tasks, phases, _ = normalize(data)
    _, doing, _ = _buckets(tasks, phases)
    if not doing:
        return None
    doing.sort(key=lambda t: (t["blocked"], _PRIORITY_RANK[t["priority"]]))
    return doing[0]


def _next_up(todo: list) -> dict | None:
    """The next task you'd pick up: earliest due, then highest priority."""
    if not todo:
        return None
    far = date.max
    return sorted(todo, key=lambda t: (t["due"] or far, _PRIORITY_RANK[t["priority"]]))[0]


def _due_chip(due, today: date) -> tuple[str, str] | None:
    if due is None:
        return None
    days = (due - today).days
    if days < 0:
        return (f"overdue {-days}d", _OVER)
    if days == 0:
        return ("due today", _GOLD)
    return (f"due in {days}d", _GOLD)


# ---- markup line builder ----------------------------------------------------
def _emit(segs: list, width: int) -> str:
    """Render (text, style|None) segments to Textual markup, escaping every text
    run and padding to `width`. Over-wide input is truncated on the last run."""
    vis = sum(len(t) for t, _ in segs)
    if vis > width:                                   # defensive: never overflow
        return _emit(_truncate(segs, width), width)
    out = []
    for t, s in segs:
        e = esc(t)
        out.append(f"[{s}]{e}[/]" if s else e)
    return "".join(out) + " " * (width - vis)


def _truncate(segs: list, width: int) -> list:
    acc, out = 0, []
    for t, s in segs:
        if acc + len(t) <= width:
            out.append((t, s))
            acc += len(t)
        else:
            out.append((t[: width - acc], s))
            break
    return out


def _fill(left: list, right: list, width: int, ch: str = "─", style: str = _DIM) -> str:
    lv = sum(len(t) for t, _ in left)
    rv = sum(len(t) for t, _ in right)
    n = max(0, width - lv - rv)
    return _emit(left + [(ch * n, style)] + right, width)


def _banner(label: str, task: dict | None, title_style, projs: dict,
            today: date, width: int, empty: str, beat: bool = False,
            nmax: int = 14) -> str:
    """One hero row: coloured spine + label + (truncated) title · project, with
    the due chip right-aligned. The title is trimmed so project + chip always fit.
    When `beat`, the row gets a faint project-tinted background wash so the task
    you're on NOW visibly breathes."""
    if not task:
        return _emit([("▐▐", _MUTED), ("  ", None), (label, "dim"),
                      ("  ", None), (empty, "dim")], width)
    nm, hx = _proj(task.get("project_id"), projs)
    nm = nm[:nmax]
    chip = _due_chip(task.get("due"), today)
    rlen = (len(chip[0]) + 1) if chip else 0
    base = 2 + 2 + len(label) + 2                     # spine + gap + label + gap
    proj = 3 + len(nm)                                # " · " + project name
    # A 26-cell card cannot carry all three of a title, a project and a due chip.
    # Rather than let `_emit` trim whichever ran off the end — which is how the
    # chip came out as "due in " with the number missing — the row gives things
    # up in a declared order. The project goes first: its colour is already on
    # the spine, so dropping the name loses the least.
    avail = width - base - proj - rlen
    if avail < 8:
        proj = 0
        avail = width - base - rlen
    if avail < 8 and chip:
        chip, rlen = None, 0
        avail = width - base
    avail = max(3, avail)
    title = task["title"]
    if len(title) > avail:
        title = title[: avail - 1] + "…"
    left = [("▐▐", hx), ("  ", None), (label, "dim"), ("  ", None),
            (title, title_style)]
    if proj:
        left += [(" · ", "dim"), (nm, hx)]
    right = [(chip[0], chip[1])] if chip else []
    row = _fill(left, right, width, ch=" ")
    return f"[on {_dark(hx)}]{row}[/]" if beat else row


# ---- renderers --------------------------------------------------------------
def _dark(hexv: str, f: float = 0.22) -> str:
    """A deep tint of a project colour, for the NOW heartbeat background wash."""
    try:
        r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return "#14202a"
    return "#%02x%02x%02x" % tuple(round(v * f) for v in (r, g, b))


def render_tile(data: dict | None, beat: bool = False) -> str:
    if not data:
        return "› [dim](no board loaded)[/dim]"
    cur = current_doing(data)
    if not cur:
        return "› [dim](nothing in progress)[/dim]"
    name, hexv = _proj(cur.get("project_id"), _projects(data))
    body = f"[dim]›[/dim] [{hexv}]{esc(name)}[/] [#ffd166]{esc(cur['title'])}[/]"
    # a doing task is alive → breathe a faint project-tinted wash on the beat
    return f"[on {_dark(hexv)}]{body}[/]" if beat else body


def render_body(data: dict | None, today: date | None = None, width: int = BODY_W,
                beat: bool = False) -> str:
    if not data:
        return ("[bold #2dd4bf]BOARD[/]\n\n"
                "[dim]no board at ~/.taskboard/board.json[/dim]\n"
                "[dim]install and run taskboard to populate this.[/dim]")
    today = today or date.today()
    W = width
    tasks, phases, report = normalize(data)
    projs = _projects(data)
    todo, doing, done = _buckets(tasks, phases)
    active = todo + doing
    now = current_doing(data)
    nxt = _next_up(todo)

    out = []
    # header — generic column labels + counts, dashed to the right
    out.append(_fill(
        [("BOARD ", "bold #2dd4bf")],
        [(" TODO ", "dim"), (str(len(todo)), None), (" · ", _DIM),
         ("DOING ", "dim"), (str(len(doing)), None), (" · ", _DIM),
         ("DONE ", "dim"), (str(len(done)), None)], W))
    out.append("")

    # NOW banner + next-up (title truncated so the project + due chip always fit)
    out.append(_banner("NOW", now, "bold #ffd166", projs, today, W,
                       empty="nothing in progress", beat=beat))
    out.append(_banner("nxt", nxt, None, projs, today, W, empty="queue empty"))
    out.append("")

    # DUE horizon
    overdue = [t for t in active if t["due"] and t["due"] < today]
    K = len(overdue)
    right = [(" ", None), ("▲ ", _OVER), (f"{K} overdue", _OVER)] if K else []
    out.append(_fill([("DUE ", "bold"), (f"─ next {_HORIZON} days ", "dim")], right, W))
    # horizon row: prefix + overdue marker + today rule + N day cells (2ch each)
    hz = [("     ", None), ("▲ " if K else "  ", _OVER if K else None), ("│", _TEAL)]
    for d in range(_HORIZON):
        day = today + timedelta(days=d)
        due_here = [t for t in active if t["due"] == day]
        if due_here:
            best = min(due_here, key=lambda t: _PRIORITY_RANK[t["priority"]])
            hz.append(("● ", _proj(best.get("project_id"), projs)[1]))
        else:
            hz.append(("· ", _DIM))
    out.append(_emit(hz, W))
    # date ticks under every other day cell (cells start at column 8)
    tick = [(" " * 8, None)]
    for d in range(0, _HORIZON, 2):
        tick.append(((today + timedelta(days=d)).strftime("%d") + "  ", "dim"))
    out.append(_emit(tick, W))
    out.append("")

    # per-project ledger — progress bar + doing/high/next-due chips
    pids = [p.get("id") for p in data.get("projects", []) or [] if isinstance(p, dict)]
    if any(t["project_id"] not in projs for t in tasks if not t["archived"]):
        pids.append(None)                                   # Inbox for orphans
    for pid in pids:
        mine = [t for t in tasks if not t["archived"] and t["project_id"] == pid]
        if not mine:
            continue
        nm, hx = _proj(pid, projs)
        d_done = sum(1 for t in mine if t["phase"] == phases[-1] and phases[-1] != phases[0])
        total = len(mine)
        fill = round(d_done / total * _BAR) if total else 0
        m_active = [t for t in mine if t["phase"] != phases[-1] or phases[-1] == phases[0]]
        doing_n = sum(1 for t in mine if t in doing)
        high_n = sum(1 for t in m_active if t["priority"] == "high")
        chips: list = []
        if doing_n:
            chips += [("▸" + str(doing_n) + " ", _GOLD)]
        if high_n:
            chips += [("!" + str(high_n) + " ", None)]      # glyph + count, no hue
        soon = [t for t in m_active if t["due"]]
        if soon:
            nd = min(soon, key=lambda t: t["due"])
            days = (nd["due"] - today).days
            chips += [(f"▲{-days}d", _OVER)] if days < 0 else [(f"d{days}", "dim")]
        row = [("▊ ", hx), (nm[:_NAMEW].ljust(_NAMEW), None), (" ", None),
               ("█" * fill, hx), ("░" * (_BAR - fill), _DIM),
               ("  ", None), (f"{d_done}/{total}", "dim"), ("  ", None)] + chips
        out.append(_emit(row, W))

    if report["rescued"]:
        out.append("")
        out.append(_emit([(f"· {report['rescued']} task(s) rescued from a format change", "dim")], W))
    return "\n".join(out)


# ---- the card seat (the deck's M/L form) ------------------------------------
# Every line here is built from (text, style) segments and emitted through
# `_emit`, which escapes each run and pads or trims it to the seat's width. That
# is not a stylistic preference: a task title comes out of a file this app does
# not own, so a title of `[red]boom[/red]` has to arrive on screen as those
# fifteen characters and not as a colour instruction.
def _card_horizon(active: list, projs: dict, today: date, w: int) -> list:
    """The due horizon, sized to the seat: as many days as the width can draw at
    two cells each. A 14-day horizon squeezed into nine days of room is a horizon
    that lies about its own span, so the header says how many days it is."""
    days = max(1, min(_HORIZON, (w - 8) // 2))
    overdue = [t for t in active if t["due"] and t["due"] < today]
    K = len(overdue)
    right = [(" ", None), ("▲ ", _OVER), (f"{K} overdue", _OVER)] if K else []
    rv = sum(len(t) for t, _ in right)
    span = [("─ next ", "dim"), (str(days), "dim"), (" days ", "dim")]
    left = [("DUE ", "bold")]
    if 4 + 14 + rv <= w:
        left += span
    out = [_fill(left, right, w)]
    hz = [("     ", None), ("▲ " if K else "  ", _OVER if K else None), ("│", _TEAL)]
    for d in range(days):
        day = today + timedelta(days=d)
        due_here = [t for t in active if t["due"] == day]
        if due_here:
            best = min(due_here, key=lambda t: _PRIORITY_RANK[t["priority"]])
            hz.append(("● ", _proj(best.get("project_id"), projs)[1]))
        else:
            hz.append(("· ", _DIM))
    out.append(_emit(hz, w))
    tick = [(" " * 8, None)]
    for d in range(0, days, 2):
        if 8 + (d // 2 + 1) * 4 <= w:            # a half-drawn date is not a date
            tick.append(((today + timedelta(days=d)).strftime("%d") + "  ", "dim"))
    out.append(_emit(tick, w))
    return out


def _card_ledger(tasks: list, phases: tuple, doing: list, projs: dict, data: dict,
                 today: date, w: int, rows: int) -> list:
    """The per-project bars, as many as the seat pays for. When there are more
    projects than rows the last row SAYS SO — a ledger that silently stops at the
    fourth project reads as a complete ledger with four projects in it."""
    # the name column yields before the chips do: a project is also named by the
    # colour of its spine, and `▲3d` is not recoverable from anything else here
    nw = max(6, min(_NAMEW, w - 26))
    bar = max(3, min(_BAR, w - nw - 14))
    pids = [p.get("id") for p in data.get("projects", []) or [] if isinstance(p, dict)]
    if any(t["project_id"] not in projs for t in tasks if not t["archived"]):
        pids.append(None)
    live = [pid for pid in pids
            if any(not t["archived"] and t["project_id"] == pid for t in tasks)]
    shown = live[:rows]
    if len(live) > rows >= 2:
        shown = live[:rows - 1]
    out = []
    for pid in shown:
        mine = [t for t in tasks if not t["archived"] and t["project_id"] == pid]
        nm, hx = _proj(pid, projs)
        d_done = sum(1 for t in mine if t["phase"] == phases[-1] and phases[-1] != phases[0])
        total = len(mine)
        fill = round(d_done / total * bar) if total else 0
        m_active = [t for t in mine if t["phase"] != phases[-1] or phases[-1] == phases[0]]
        doing_n = sum(1 for t in mine if t in doing)
        high_n = sum(1 for t in m_active if t["priority"] == "high")
        c_doing = ("▸" + str(doing_n) + " ", _GOLD) if doing_n else None
        c_high = ("!" + str(high_n) + " ", None) if high_n else None
        soon = [t for t in m_active if t["due"]]
        c_due = None
        if soon:
            nd = min(soon, key=lambda t: t["due"])
            dd = (nd["due"] - today).days
            c_due = (f"▲{-dd}d", _OVER) if dd < 0 else (f"d{dd}", "dim")
        chips = [c for c in (c_doing, c_high, c_due) if c]
        row = [("▊ ", hx), (nm[:nw].ljust(nw), None), (" ", None),
               ("█" * fill, hx), ("░" * (bar - fill), _DIM),
               ("  ", None), (f"{d_done}/{total}", "dim"), ("  ", None)]
        lv = sum(len(t) for t, _ in row)
        # A chip is dropped WHOLE and in a declared order, so a narrow seat never
        # halves one. Priority goes first and the date goes last: `!1` is a
        # standing property of the work, an overdue date is a fact about today.
        for victim in (c_high, c_doing, c_due):
            if lv + sum(len(t) for t, _ in chips) <= w:
                break
            if victim:
                chips.remove(victim)
        out.append(_emit(row + chips, w))
    if len(live) > len(shown) and len(out) < rows:
        out.append(_emit([(f"  · {len(live) - len(shown)} more project(s)", "dim")], w))
    # the block never renders empty — an empty ledger looks like a broken one
    return out or [_emit([("· no projects on the board", "dim")], w)]


def card_fields(data: dict | None, w: int, h: int, want: int,
                today: date | None = None, beat: bool = False,
                head: str = "[bold #2dd4bf]BOARD[/]"):
    """[(declared field, [line, ...]), ...] — the first `want` fields of the
    board card, in `deck.CARD_FIELDS` order."""
    today = today or date.today()
    # `_emit` truncates by recursing on its own over-wide output, so a NEGATIVE
    # width never converges — `t[:width - acc]` keeps handing it a shorter string
    # that is still wider than the target. The seat cannot produce one, but the
    # seat is not the only caller a renderer ever gets.
    w = max(0, w)
    if not data:
        hint = ("install and run taskboard to fill this" if w >= 38
                else "run taskboard to fill this" if w >= 27 else "run taskboard")
        blank = {"now": [_emit([("no board at ~/.taskboard/board.json", "dim")], w),
                         _emit([(hint, "dim")], w)],
                 "horizon": ["", "", ""], "ledger": [""], "detail": [""]}
        return [(n, [head] if n == "head" else blank[n])
                for n in deck.CARD_FIELDS["board"][:want]]

    tasks, phases, report = normalize(data)
    projs = _projects(data)
    todo, doing, done = _buckets(tasks, phases)
    active = todo + doing
    out = []
    for idx, name in enumerate(deck.CARD_FIELDS["board"][:want]):
        if name == "head":
            out.append((name, [head]))
        elif name == "now":
            nmax = max(4, min(14, w // 3))
            out.append((name, [
                _banner("NOW", current_doing(data), "bold #ffd166", projs, today,
                        w, empty="nothing in progress", beat=beat, nmax=nmax),
                _banner("nxt", _next_up(todo), None, projs, today, w,
                        empty="queue empty", nmax=nmax)]))
        elif name == "horizon":
            out.append((name, _card_horizon(active, projs, today, w)))
        elif name == "ledger":
            out.append((name, _card_ledger(
                tasks, phases, doing, projs, data, today, w,
                deck.room(h, "board", idx, want))))
        else:
            segs = ([(f"· {report['rescued']} task(s) rescued from a format change", "dim")]
                    if report["rescued"] else
                    [(f"· {len(active)} active · {len(done)} done", "dim")])
            out.append((name, [_emit(segs, w)]))
    return out


def render_card(data: dict | None, w: int, h: int, want: int,
                today: date | None = None, beat: bool = False,
                head: str = "[bold #2dd4bf]BOARD[/]") -> str:
    return "\n".join(l for _n, ls in card_fields(data, w, h, want, today, beat, head)
                     for l in ls)
