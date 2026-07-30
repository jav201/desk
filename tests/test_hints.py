"""Key hint bar: it must fit any width, never hide the essential keys, admit
when it truncated, and change with the open panel.

WHY these matter: Textual's Footer silently dropped `q` (quit) at 80 columns and
`F5` at 60 in this app, and never changed between panels — which made a narrow
always-on-top deck unusable. Each assertion below pins one of those failures.
"""
from __future__ import annotations

import re

from desk import hints

MODES = ("strip", "board", "focus", "capture", "record", "close")
WIDTHS = range(30, 121)


def _plain(markup: str) -> str:
    return re.sub(r"\[/?[^\]]*\]", "", markup)


def test_never_overflows_at_any_width():
    """AC-1: the visible line always fits the width it was given — a hint bar
    that overflows would wrap and break the one-row dock."""
    for mode in MODES:
        for w in WIDTHS:
            vis = len(_plain(hints.render(mode, w)))
            assert vis <= w, f"{mode} at {w}: rendered {vis} cols"


def test_reported_visible_width_matches_the_render():
    """The helper tests use visible_width; it must not drift from render()."""
    for mode in MODES:
        for w in (30, 47, 80, 120):
            assert hints.visible_width(mode, w) == len(_plain(hints.render(mode, w)))


def test_quit_is_never_dropped_where_it_works():
    """AC-2: quit vanished from the Footer at 80 cols. It must survive every
    width in every mode where the key actually fires. Capture is excluded on
    purpose: its text box has focus, so `q` types a 'q' — advertising it there
    would be a lie (see test_capture_only_shows_keys_that_work)."""
    for mode in ("strip", "board", "focus", "record"):
        for w in WIDTHS:
            assert " quit" in _plain(hints.render(mode, w)), f"{mode} at {w}"


def test_capture_only_shows_keys_that_work():
    """In capture the Input holds focus, so only non-text keys do anything.
    The bar must show enter/esc and NOT the letter hotkeys that would just be
    typed into the note."""
    for w in WIDTHS:
        plain = _plain(hints.render("capture", w))
        assert "save" in plain and "esc" in plain      # the keys that work
        assert "board" not in plain and "quit" not in plain  # would be typed, not fired


def test_escape_is_never_dropped_inside_a_panel():
    """AC-2: inside a panel, collapsing back to the strip is essential."""
    for mode in ("board", "focus", "capture", "record"):
        for w in WIDTHS:
            assert "esc" in _plain(hints.render(mode, w)), f"{mode} at {w}"


def test_truncation_is_announced_not_silent():
    """AC-3: the Footer's sin was hiding keys with no sign. When we drop hints,
    the line must say so."""
    narrow = _plain(hints.render("strip", 32))
    assert "…" in narrow                       # truncation marker present
    full = _plain(hints.render("strip", 120))
    assert "…" not in full                     # nothing dropped -> no marker
    # and the marker only appears when something really was dropped
    sel_narrow, ell_narrow = hints.fit("strip", 32)
    sel_full, ell_full = hints.fit("strip", 120)
    assert ell_narrow is True and ell_full is False
    assert len(sel_narrow) < len(sel_full)


def test_hints_are_context_specific_per_panel():
    """AC-4: the whole point — the bar must differ per mode."""
    W = 120
    strip = _plain(hints.render("strip", W))
    focus = _plain(hints.render("focus", W))
    record = _plain(hints.render("record", W))
    capture = _plain(hints.render("capture", W))
    board = _plain(hints.render("board", W))
    assert "start/pause" in focus and "skip" in focus and "reset" in focus
    assert "rec/stop" in record and "auto-stop" in record
    assert "save" in capture
    assert "open board" in board and "refresh" in board
    assert "board" in strip and "focus" in strip and "record" in strip
    assert len({strip, focus, record, capture, board}) == 5      # all distinct


def test_dropping_prefers_the_least_important_hint():
    """Lower-priority hints go first: at a width that fits only some of the strip
    legend, the panel keys (priority 1) outlive `o`/`t` (priority 3)."""
    sel, _ = hints.fit("strip", 46)
    keys = [k for k, _, _ in sel]
    assert "q" in keys                         # essential
    assert "b" in keys                         # priority 1 survives
    assert "o" not in keys and "t" not in keys  # priority 3 dropped first


def test_only_width_1_glyphs():
    """AC-6: a wide glyph would desynchronise the one-row dock."""
    import unicodedata
    for mode in MODES:
        for ch in _plain(hints.render(mode, 120)):
            assert unicodedata.east_asian_width(ch) not in ("W", "F"), repr(ch)
