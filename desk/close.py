"""The day-close (`d`) — a surface that counts a day owes the day an ending.

desk spends all day adding up. Without a close it never says what the sum was,
and the pomodoro count silently resets. This is the closing entry.

EVERY FIGURE HERE IS READ FROM ~/.desk/pomodoros.jsonl. There is no other
source: `state.json` holds the live timer and no timestamp at all, so before the
journal existed nothing on this screen could have been true. When the journal has
nothing for today the screen says so and prints NO NUMBER — an empty day renders
as an empty day, not as a row of zeroes dressed up as a result.

THE HERO IS THE DAY'S FIRE: twenty-four hours as one braille field, each hour a
column whose height is the minutes spent in it. It is read as a shape, not as a
table — where the day was hot, where it went out. The unlit track is drawn, so
the band is a full field at 8 minutes as well as at 8 hours.

The register is desk's: it reports the day, it does not grade it.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta

from rich.markup import escape as esc

from . import focus

BRIGHT = "#dbe4ee"
INK = "#c9d4e0"
TEAL = "#2dd4bf"
GOLD = "#ffd166"
ASH = "#8a5a4a"
DIM = "#5b6675"
MUT = "#6b7787"

BAND_ROWS = 7                  # the hero's height in cell-rows
HOUR_CELLS = 2                 # braille cells per hour -> 48 cells wide
_BIT = {(0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (0, 3): 0x40,
        (1, 0): 0x08, (1, 1): 0x10, (1, 2): 0x20, (1, 3): 0x80}


MAX_SECONDS = 24 * 3600        # an "interval" longer than a day is not one


def read_journal(path=None) -> list[dict]:
    """Every well-formed record in the journal. Never raises: a missing file is
    an empty day, and one corrupt line costs that line and nothing else — a
    close that crashes on a half-written record is worse than a close that is
    one interval short.

    EVERY FIELD IS COERCED HERE, at the trust boundary, because this is where
    the guarantee above is either kept or merely claimed. The first version
    validated only that the line was a dict with a parseable `ended_at`, so a
    line that was perfectly good JSON with `"seconds": "1500"` — or `null`, or
    `[1]`, or `1e999`, or `NaN` — sailed through and detonated later in the
    arithmetic. Because the journal is append-only and has no repair path, ONE
    such line made `d` crash the app forever. `Pomodoro.load` already sets the
    rule for this module: clamp and cast everything you read off disk."""
    path = path or focus.JOURNAL_PATH
    out = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if not (isinstance(rec, dict) and rec.get("ended_at")):
                continue
            secs = rec.get("seconds", 0)
            # REJECT, do not repair. `float("1500")` would succeed and quietly
            # accept a record desk never writes — and reinterpreting a value
            # whose TYPE is wrong is a confident guess about a file that some
            # other tool produced. `bool` is excluded because it is an int.
            if isinstance(secs, bool) or not isinstance(secs, (int, float)):
                continue
            if not math.isfinite(secs) or not 0 <= secs <= MAX_SECONDS:
                continue                             # inf, NaN, negative, absurd
            secs = float(secs)
            rec["seconds"] = secs
            rec["outcome"] = str(rec.get("outcome", ""))
            rec["_ended"] = datetime.fromisoformat(rec["ended_at"])
            out.append(rec)
        except Exception:
            continue
    return out


def stats(rows: list[dict], day: date | None = None) -> dict:
    """The day's figures. `by_hour` is minutes per hour of the clock and is the
    only one the hero reads; the rest are the lines under it."""
    day = day or date.today()
    mine = [r for r in rows if r["_ended"].date() == day]
    by_hour = [0.0] * 24
    for r in mine:
        by_hour[r["_ended"].hour] += r.get("seconds", 0) / 60.0
    active = [h for h in range(24) if by_hour[h] > 0]
    return {
        "day": day,
        "intervals": len(mine),
        "completed": sum(1 for r in mine if r.get("outcome") == "completed"),
        "skipped": sum(1 for r in mine if r.get("outcome") == "skipped"),
        "minutes": sum(by_hour),
        "by_hour": by_hour,
        "best_hour": max(active, key=lambda h: by_hour[h]) if active else None,
        "worst_hour": min(active, key=lambda h: by_hour[h]) if active else None,
        "streak": _streak(rows, day),
    }


def _streak(rows: list[dict], day: date) -> int:
    """Consecutive days ending today that carried at least one completion.

    It starts at YESTERDAY when today is still empty, so opening the close at
    09:00 does not report a run of four as broken before the day has begun.
    A streak is a fact about the past; today is not over yet."""
    done = {r["_ended"].date() for r in rows if r.get("outcome") == "completed"}
    if not done:
        return 0
    cur = day if day in done else day - timedelta(days=1)
    n = 0
    while cur in done and n < 3660:            # bounded: ten years is plenty
        n += 1
        cur -= timedelta(days=1)
    return n


def hour_band(by_hour: list[float], rows: int = BAND_ROWS) -> list[str]:
    """The day as a fire across twenty-four hours.

    One column per hour, filled from the floor up: a BOUNDARY THAT MOVES, so an
    hour with 40 minutes and an hour with 20 look different — which a scatter
    over the same cells would not.

    THE TRACK IS A LATTICE, NOT A WALL. The first build drew unlit cells as a
    full braille block in ash and lit ones as a full block in gold: identical
    GLYPHS separated only by colour, so in greyscale the whole hero was one
    solid rectangle and the three states of the day were indistinguishable. The
    unlit track now carries one dot per cell — present, so a quiet day is still
    a field rather than three marks floating on black, and under a quarter of
    the cell, so the fire is the only thing that reads as mass."""
    H = rows * 4
    track = _BIT[(0, 1)]                               # one dot: the unlit lattice
    out = []
    for cy in range(rows):
        cells = []
        for hour in range(24):
            lit = min(1.0, by_hour[hour] / 60.0) * H
            for _ in range(HOUR_CELLS):
                mask_on = 0
                for y in range(4):
                    dy = cy * 4 + y
                    height = H - dy                    # dot row 0 is the top
                    for x in range(2):
                        if height <= lit:
                            mask_on |= _BIT[(x, y)]
                if mask_on:
                    cells.append((chr(0x2800 + mask_on), GOLD))
                else:
                    cells.append((chr(0x2800 + track), ASH))
        row, j = "", 0
        while j < len(cells):
            col = cells[j][1]
            k = j
            while k < len(cells) and cells[k][1] == col:
                k += 1
            chunk = "".join(cells[i][0] for i in range(j, k))
            row += f"[{col}]{chunk}[/]" if col else chunk
            j = k
        out.append("  " + row)
    return out


def _hh(hour: int) -> str:
    return f"{hour:02d}:00"


def hour_axis() -> str:
    """The band's ruler, built to the band's OWN width rather than typed out —
    a hand-written axis was 86 characters under a 48-cell band, and every row of
    a drawn figure has to be exactly as long as the others or the figure stops
    reading as one."""
    w = 24 * HOUR_CELLS
    line = ["·"] * w
    for hour in (0, 6, 12, 18):
        label = f"{hour:02d}"
        at = hour * HOUR_CELLS
        line[at:at + 2] = list(label)
    line[w - 2:w] = list("23")
    return "  [dim]" + "".join(line) + "[/dim]"


def render_body(rows: list[dict] | None = None, day: date | None = None) -> str:
    """The close screen as Textual markup."""
    st = stats(rows if rows is not None else read_journal(), day)
    out = [f"[bold {TEAL}]CLOSE[/]  [dim]{st['day']:%a %d %b}[/dim]", ""]

    if not st["intervals"]:
        # THE EMPTY STATE, AND IT PRINTS NO FIGURE. Rendering zeroes here would
        # be a table of results for a day that has none — the difference between
        # a ledger with no entries and a ledger claiming a total of nothing.
        out += hour_band([0.0] * 24)
        out.append(hour_axis())          # the instrument, with nothing on it yet
        if focus.JOURNAL_ERROR:
            # An empty day and a day whose journal could not be WRITTEN look
            # identical from here, and only one of them is the operator's day.
            out += ["", f"    [{MUT}]the journal could not be written[/]",
                    f"    [dim]{esc(focus.JOURNAL_ERROR)}[/dim]",
                    f"    [dim]intervals are being counted and not kept[/dim]"]
            return "\n".join(out)
        out += ["", f"    [{MUT}]the journal opens today[/]",
                f"    [dim]intervals are written when they end;"
                f" nothing has ended yet[/dim]"]
        if st["streak"]:
            out.append(f"    [dim]{st['streak']} day(s) before this one carried"
                       f" work[/dim]")
        return "\n".join(out)

    out += hour_band(st["by_hour"])
    out.append(hour_axis())
    out.append("")
    mins = int(round(st["minutes"]))
    out.append(f"    [{BRIGHT}]{mins}[/] [dim]minutes[/dim]   "
               f"[{GOLD}]{st['completed']}[/] [dim]completed[/dim]   "
               f"[{MUT}]{st['skipped']}[/] [dim]skipped[/dim]")
    if st["best_hour"] is not None:
        best = f"[{TEAL}]{_hh(st['best_hour'])}[/] [dim]was the hot hour[/dim]"
        line = f"    {best}"
        if st["worst_hour"] != st["best_hour"]:
            line += (f"   [{DIM}]{_hh(st['worst_hour'])}[/] "
                     f"[dim]the thinnest[/dim]")
        out.append(line)
    if st["streak"]:
        out.append(f"    [dim]{st['streak']} day(s) running[/dim]")
    out.append("")
    out.append(f"    [dim]nothing deleted · the journal keeps every interval[/dim]")
    return "\n".join(out)
