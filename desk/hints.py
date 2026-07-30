"""Bottom hint bar — a width-aware, context-aware key legend.

Textual's `Footer` lays its keys out left-to-right and simply drops whatever does
not fit, with no indication. Measured on textual 8.2.8 in this app: `q` (quit)
disappeared at 80 columns, `F5` (refresh) at 60, and the Record key at 40 — fatal
for a deliberately narrow always-on-top widget, and the reason the deck felt
unusable. The Footer also never changed, because every panel control is
`show=False`, so the same legend showed in strip mode and inside all four panels.

This renders the legend ourselves instead:
  * each hint carries a PRIORITY; priority 0 (quit, and `esc` inside a panel) is
    kept no matter how narrow the window gets,
  * hints are dropped worst-priority-first (rightmost among ties) until the line
    fits the available width,
  * if anything was dropped the line ends with an ellipsis, so truncation is
    VISIBLE rather than silent,
  * the set of hints depends on the open panel, so the bar is actually useful.
"""
from __future__ import annotations

KEY = "#ffd166"          # key cap colour (desk's gold accent)
_SEP_VIS = 3             # visible width of the " · " separator
_ELL_VIS = 2             # visible width of the " …" truncation marker

# (key, label, priority) in DISPLAY order. priority 0 == never dropped.
_PANEL_KEYS = ("b/f/c/m", "panels", 2)
_QUIT = ("q", "quit", 0)
_ESC = ("esc", "strip", 0)

_CONTEXT = {
    "focus": [("space", "start/pause", 1), ("s", "skip", 2),
              ("r", "reset", 2), ("+/-", "set", 3)],
    "record": [("space", "rec/stop", 1), ("i", "file", 2), ("u", "url", 2),
               ("a", "auto-stop", 2), ("t", "scripts", 3)],
    "board": [("o", "open board", 2), ("F5", "refresh", 2)],
    # the close is read-only: there is nothing to press but the way out.
    "close": [],
    # "capture" is handled specially in hints_for (its text box holds focus).
}


def hints_for(mode: str) -> list[tuple[str, str, int]]:
    """The candidate hints for a mode, in display order."""
    if mode == "strip":
        return [("b", "board", 1), ("f", "focus", 1), ("c", "capture", 1),
                ("m", "record", 1), ("d", "close day", 2),
                ("F5", "refresh", 2), ("o", "open", 3),
                ("t", "scripts", 3), _QUIT]
    if mode == "capture":
        # the text box holds focus here, so letter keys type into the note and
        # only the non-text keys actually work — advertise ONLY those, or the
        # bar would promise b/f/c/m/q that just get typed.
        return [("enter", "save", 1), _ESC]
    return _CONTEXT.get(mode, []) + [_PANEL_KEYS, _ESC, _QUIT]


def _w(item: tuple[str, str, int]) -> int:
    return len(item[0]) + 1 + len(item[1])          # "key label"


def _total(sel: list, ell: bool) -> int:
    if not sel:
        return _ELL_VIS if ell else 0
    return (sum(_w(i) for i in sel) + _SEP_VIS * (len(sel) - 1)
            + (_ELL_VIS if ell else 0))


def fit(mode: str, width: int) -> tuple[list, bool]:
    """Select the hints that fit `width`. Returns (selection, truncated)."""
    sel = list(hints_for(mode))
    ell = False
    while sel and _total(sel, ell) > width:
        droppable = [i for i, it in enumerate(sel) if it[2] > 0]
        if droppable:
            worst = max(sel[i][2] for i in droppable)
            idx = max(i for i in droppable if sel[i][2] == worst)
        else:
            if len(sel) == 1:       # only the last essential left: keep it
                break
            idx = 0                 # shed essentials from the front, quit last
        sel.pop(idx)
        ell = True
    return sel, ell


def render(mode: str, width: int) -> str:
    """The hint bar as Textual markup, guaranteed to fit `width`."""
    sel, ell = fit(mode, max(0, width))
    parts = [f"[{KEY}]{k}[/] [dim]{label}[/dim]" for k, label, _ in sel]
    out = " [dim]·[/dim] ".join(parts)
    if ell:
        out = (out + " [dim]…[/dim]") if out else "[dim]…[/dim]"
    return out


def visible_width(mode: str, width: int) -> int:
    """Visible (tag-free) width of what `render` would produce — for tests."""
    sel, ell = fit(mode, max(0, width))
    return _total(sel, ell)
