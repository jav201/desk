"""The card seats — what each panel becomes when the deck hands it a box.

`tests/test_deck_geometry.py` proves the arithmetic and `tests/test_deck_wiring.py`
proves the app obeys it. Neither can see what is DRAWN inside the box, and the
whole of increment 1 shipped with four cards rendering the same one-line glance
at every size while both files stayed green.

The laws here are about the seat's contract rather than about taste:

  - THE PREFIX. A card draws the first `want` fields `deck.CARD_FIELDS` declares
    and stops. Not a subset, not a reordering — a prefix, so that growing a card
    by one row adds the next thing and moves nothing that was already there.
  - THE FLOOR. A field that is drawn is drawn whole. Half a due chip and three
    rows of a four-row clock are not smaller versions of those things.
  - THE CEILING. `<= h` lines and `<= w` cells, measured in CELLS: a braille dot
    and a CJK glyph are not both one column, and a card that measures itself in
    characters overflows its seat on the first wide one.

The (h, want) and width sets every law quantifies over are SWEPT out of
`desk.app.seats` rather than listed by hand. A hand-listed fixture cannot fail
when the geometry changes underneath it, which is the failure mode
`test_deck_wiring.py` names in its own opening paragraph.
"""
from __future__ import annotations

import inspect
import json
import re
from datetime import date, timedelta

import pytest
from rich.cells import cell_len

from desk import board, capture, deck, focus, record
from desk.app import Deck, seats

_TAG = re.compile(r"(?<!\\)\[/?[^\]]*\]")


def _plain(line: str) -> str:
    """What the terminal actually paints: markup tags gone, and an ESCAPED
    bracket restored to the one character it prints as.

    The lookbehind is the whole point. A naive `\\[/?[^\\]]*\\]` strips the tag
    out of `\\[red]` and leaves a bare backslash, so a line carrying a poisoned
    task title measures 6 cells where the terminal will paint 15 — and the width
    law would pass on exactly the line most likely to overflow."""
    return _TAG.sub("", line).replace("\\[", "[")


def _vis(line: str) -> int:
    return cell_len(_plain(line))


# ---- the swept case set -----------------------------------------------------
def _sweep():
    """{card: {(w, h, want)}} over every seat the deck can hand out above S."""
    cases: dict = {c: set() for c in deck.DECK_ORDER}
    for w in range(30, 201):
        for h in range(4, 61):
            tname, seat, _shown, _shed = seats(w, h)
            if tname == deck.TIER_S:
                continue                       # S is the glance form, not a card
            for card, (_x, _y, cw, ch) in seat.items():
                cases[card].add((cw, ch, deck.deck_want(card, ch, tname)))
    return cases


CASES = _sweep()
HW = {c: sorted({(h, want) for _w, h, want in v}) for c, v in CASES.items()}
WIDTHS = {c: sorted({w for w, _h, _want in v}) for c, v in CASES.items()}
SAMPLE_W = (26, 27, 38, 58, 98)

TODAY = date(2026, 7, 30)
POISON = "[red]boom[/red]"
BOARD_DATA = {
    "projects": [{"id": "p1", "name": "Guitar Bass Lab", "color": "cyan"},
                 {"id": "p2", "name": "[bold]evil[/bold]", "color": "amber"},
                 {"id": "p3", "name": "desk", "color": "violet"}],
    "tasks": [
        {"id": "a", "title": "wire the deck seats", "project_id": "p3",
         "status": "doing", "priority": "high", "due_date": "2026-08-01"},
        {"id": "b", "title": POISON, "project_id": "p1", "status": "backlog",
         "priority": "high", "due_date": "2026-07-27"},
        {"id": "c", "title": "k3s on bare metal", "project_id": "p2",
         "status": "backlog", "due_date": "2026-08-04"},
        {"id": "d", "title": "a finished thing", "project_id": "p3", "status": "done"},
        {"id": "e", "title": "an orphan", "status": "backlog"},
    ]}
POMO = focus.Pomodoro(remaining=754, running=True, completed=2)
TRANSCRIPT = "the quarterly numbers are confidential until thursday"


def _fields(card: str, w: int, h: int, want: int, data=BOARD_DATA):
    if card == "board":
        return board.card_fields(data, w, h, want, today=TODAY)
    if card == "focus":
        return focus.card_fields(POMO, w, h, want, phase=1)
    if card == "capture":
        return capture.card_fields(capture.pick_prompt(0), "2026-07-30.md",
                                   w, h, want)
    return record.card_fields("recording", 143.0, 0.06, w, h, want)


def _card(card: str, w: int, h: int, want: int, data=BOARD_DATA) -> str:
    if card == "board":
        return board.render_card(data, w, h, want, today=TODAY)
    if card == "focus":
        return focus.render_card(POMO, w, h, want, phase=1)
    if card == "capture":
        return capture.render_card(capture.pick_prompt(0), "2026-07-30.md",
                                   w, h, want)
    return record.render_card("recording", 143.0, 0.06, w, h, want)


def test_the_swept_case_set_is_itself_worth_quantifying_over():
    """THE ORACLE ON THE ORACLE. Every law below is only as strong as this set,
    and a sweep that silently collapsed to one shape would make all of them
    green and meaningless. Three things have to hold: the narrowest card the
    deck really produces is in it, more than one `want` is in it (or the prefix
    law is testing a constant), and every card is represented."""
    for card in deck.DECK_ORDER:
        assert CASES[card], card
        assert 26 in WIDTHS[card], f"{card} never sees deck.CARD_MIN"
        assert 27 in WIDTHS[card], f"{card} never sees the 58x14 width"
        assert len({want for _h, want in HW[card]}) > 1, (
            f"{card} only ever asks for {HW[card]} — the prefix law is a constant")
    assert deck.CARD_MIN == 26
    assert seats(86, 24)[1]["board"][2] == 26      # where that width comes from
    assert seats(58, 14)[1]["board"][2] == 27


@pytest.mark.parametrize("card", deck.DECK_ORDER)
def test_a_card_draws_the_declared_prefix_and_stops(card):
    """AT-02. The field names, in order, are `CARD_FIELDS[card][:want]` — nothing
    renamed, nothing reordered, nothing skipped in the middle. Skipping a middle
    field is the subtle one: it still looks like a card, and it makes the row
    budget of every field after it a fiction."""
    for h, want in HW[card]:
        for w in SAMPLE_W:
            got = [n for n, _lines in _fields(card, w, h, want)]
            assert tuple(got) == deck.CARD_FIELDS[card][:want], (
                f"{card} at {w}x{h} want={want}: {got}")


@pytest.mark.parametrize("card", deck.DECK_ORDER)
def test_every_field_drawn_is_drawn_whole_and_the_card_fits_its_rows(card):
    """AT-02b. "Renounced, never truncated" is not observable as a claim; it is
    observable as a floor. A field present with fewer rows than
    `deck.FIELD_MIN` is a truncated field whatever the renderer meant, and the
    variable block is the one that can silently reach zero — which is the exact
    defect `test_deck_geometry.py:85` guards on the arithmetic side and could
    not see on the rendering side."""
    var = deck.VARIABLE_FIELD[card]
    for h, want in HW[card]:
        for w in SAMPLE_W:
            fields = _fields(card, w, h, want)
            total = 0
            for name, lines in fields:
                assert len(lines) >= deck.FIELD_MIN[card][name], (
                    f"{card}.{name} at {w}x{h} want={want}: {len(lines)} rows "
                    f"< floor {deck.FIELD_MIN[card][name]}")
                if name != var:
                    assert len(lines) == deck.FIELD_MIN[card][name], (
                        f"{card}.{name} is not the variable block but spent "
                        f"{len(lines)} rows at {w}x{h}")
                total += len(lines)
            assert total <= h, f"{card} at {w}x{h} drew {total} rows into {h}"
            if want > deck.CARD_FIELDS[card].index(var):
                assert dict(fields).get(var), (
                    f"{card}.{var} rendered empty (or not at all) at {w}x{h}")


@pytest.mark.parametrize("card", deck.DECK_ORDER)
def test_no_line_is_wider_than_the_seat(card):
    """AT-02c. Swept over EVERY width the deck hands this card, because the
    narrow end is where the interesting failures are: 26 cells is not enough for
    the focus panel's 30-cell carved clock, for board's 14-day horizon, or for
    the capture prompt. Measured in cells rather than characters."""
    over = []
    for w, h, want in sorted(CASES[card]):
        for line in _card(card, w, h, want).split("\n"):
            if _vis(line) > w:
                over.append((w, h, want, _vis(line), _plain(line)))
    assert not over, over[:4]


@pytest.mark.parametrize("card", deck.DECK_ORDER)
def test_the_card_never_raises_at_any_size_it_could_be_handed(card):
    """A renderer that is only ever called from the seat is still called from a
    resize race, from a 0x0 window before the first layout, and from the next
    test somebody writes. `board._emit` truncates by recursing on its own output
    and never converges on a negative width — which is a RecursionError inside a
    paint, not a wrong pixel."""
    for w in range(-2, 201, 7):
        for h in range(0, 61, 3):
            want = deck.deck_want(card, max(0, h), deck.TIER_L)
            _card(card, w, h, want)


# ---- the seat the app actually paints ---------------------------------------
async def test_the_S_deck_is_still_the_glance_form():
    """The one place `want` must NOT be spent as a field count. At S
    `deck.deck_want` returns `TIER_PREFIX["S"]`, which is a ROW budget — read as
    a field count it asks Focus for a four-row ember floor inside a two-row
    card. S is the head and the strip line, and that is the whole form."""
    app = Deck()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(40, 12)
        await pilot.pause()
        assert deck.tier(40, 12) == deck.TIER_S
        text = app._card_text("focus", 38, 2, app._tiles(), deck.TIER_S)
        assert text.split("\n") == [app._card_head("focus", 38),
                                    focus.render_tile(app.pomo, beat=app._beat)]


async def test_the_focus_card_says_whether_the_clock_is_running():
    """AT-02d, through the real app at its default size. The card is 38 cells
    wide there and the carved clock is 30 of them, so the fire is what the panel
    LOOKS like and the run mark is the only thing that says, in one glyph, that
    the timer is moving. `tests/test_focus.py:65` already depends on the running
    half of this."""
    app = Deck()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.pomo.running is False
        await pilot.press("space")
        await pilot.pause()
        assert app.pomo.running is True
        assert "▸" in str(app.query_one("#tile-focus").render())
        await pilot.press("space")
        await pilot.pause()
        assert app.pomo.running is False
        assert "▸" not in str(app.query_one("#tile-focus").render())


async def test_the_breath_reaches_the_card_and_only_while_it_runs():
    """AT-05 — the same trick as `tests/test_motion.py:85`, moved onto the CARD.
    A `phase` the panel computes and the deck never passes is a still ember with
    a fully green suite, and the card is a second call site that can drop it
    independently of the panel.

    THE CLOCK IS PINNED so the phase is the only thing that can move, and the
    frames are compared with markup STRIPPED so a breath living only in a hex
    value counts as no breath at all."""
    app = Deck()
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause()
        assert deck.tier(120, 34) == deck.TIER_L
        await pilot.press("f")
        await pilot.press("space")
        await pilot.pause()
        seen = set()
        for _ in range(focus.EMBER_PHASES):
            app.pomo.remaining = 701              # pinned: the tick makes it 700
            app._tick()
            await pilot.pause()
            assert app.pomo.remaining == 700, "the clock moved — control broken"
            seen.add(_plain(str(app.query_one("#tile-focus").render())))
        assert len(seen) == focus.EMBER_PHASES, (
            f"{len(seen)} distinct card frames over a full loop with the clock "
            "pinned — the ambient is not reaching the seat")

        await pilot.press("space")                # and stillness is a state
        await pilot.pause()
        assert app.pomo.running is False
        still = set()
        for _ in range(focus.EMBER_PHASES):
            app.pomo.remaining = 700
            app._tick()
            await pilot.pause()
            still.add(_plain(str(app.query_one("#tile-focus").render())))
        assert len(still) == 1, "a stopped timer's card is still breathing"


def test_the_fires_ramp_is_spent_only_at_the_declared_seats(monkeypatch):
    """AT-07 — the hue ration, at the new call site.
    `tests/test_hue_ration.py:73` declares which functions may tint with the
    temperature ramp, and it can only see the two renderers that existed when it
    was written. `render_card` is a third one, and a card that reached for
    `temp_hex` directly would paint a task-shaped thing in the fire's colours
    without any existing law noticing."""
    seen = set()
    real = focus.temp_hex

    def spy(frac):
        # `inspect.stack()[1].function` — the idiom test_hue_ration.py uses —
        # walks and materialises EVERY frame on every one of ~15 000 calls here,
        # which costs this law 80 seconds by itself. `f_back.f_code.co_name` is
        # the same string in O(1), and the first call PROVES it is rather than
        # leaving the substitution as a claim in a comment.
        name = inspect.currentframe().f_back.f_code.co_name
        if not seen:
            assert name == inspect.stack()[1].function
        seen.add(name)
        return real(frac)

    monkeypatch.setattr(focus, "temp_hex", spy)
    for w, h, want in sorted(CASES["focus"]):
        focus.render_card(POMO, w, h, want, phase=1)
    from test_hue_ration import RAMP_SEATS       # the declaration, not a copy
    assert seen <= RAMP_SEATS, f"the fire's ramp leaked into: {seen - RAMP_SEATS}"
    assert seen, "the spy never fired — the law is measuring nothing"


def test_a_poisoned_task_title_is_painted_and_not_obeyed():
    """The security half. A title and a project name come out of
    `~/.taskboard/board.json`, a file desk neither writes nor validates, and they
    land in a markup language. `[red]boom[/red]` has to arrive as those fifteen
    characters."""
    hit = 0
    for w, h, want in sorted(CASES["board"]):
        out = _card("board", w, h, want)
        assert "[red]boom[/red]" not in _TAG.sub("", out), (
            f"the title was obeyed as markup at {w}x{h}")
        if want >= 2 and w >= 40:
            assert "\\[red]" in out, f"the title vanished at {w}x{h} want={want}"
            hit += 1
    assert hit, "no seat ever drew the poisoned title — the law is vacuous"
    # and the same for a project name, which reaches the ledger by another path
    wide = _card("board", 58, 13, 5)
    assert "\\[bold]evil" in wide, wide


def test_the_transcript_never_reaches_the_deck():
    """`record.render_body` shows 220 characters of the last meeting transcript.
    `CARD_FIELDS["record"]` deliberately has no field for it, and the deck sits
    on top of every other window — including while somebody else is looking at
    the screen. Asserted rather than assumed, because folding it into `state`
    would be a one-line change that looks like an improvement."""
    assert TRANSCRIPT in record.render_body("idle", last=TRANSCRIPT)
    # the card has no PARAMETER for it, which is the form of the guarantee that
    # cannot be undone by a renderer change alone
    assert "last" not in inspect.signature(record.render_card).parameters
    for w, h, want in sorted(CASES["record"]):
        out = record.render_card("idle", 0.0, 0.0, w, h, want)
        assert "confidential" not in out and "quarterly" not in out, (w, h, want)
