"""The deck, WIRED: the geometry seat governs the running app.

`tests/test_deck_geometry.py` proves the arithmetic in `desk/deck.py` is right.
It cannot prove the app reads it — and for the whole life of that module the app
did not, while every one of its laws stayed green. These are the laws that can
only fail in a running app: a card placed where the seat did not put it, a card
shed without being named, a chrome row taken from the deck's body.

The regions below are GOLDEN LITERALS, measured once and pasted. That is
deliberate: a test that recomputes the expected position from the same helper
the app uses agrees with the app by construction, including when both are wrong.
A literal cannot be co-mutated with the code.
"""
from __future__ import annotations

import re

import pytest

from desk import deck, hints
from desk.app import RIBBON_SHED, Deck, seats

# (w, h) -> (tier, cols, shed, {card: (x, y_in_deck, w, h)})
GOLDEN = {
    (30, 8): ("S", 1, ("capture", "record"),
              {"board": (1, 0, 28, 2), "focus": (1, 3, 28, 2)}),
    (40, 12): ("S", 1, ("capture",),
               {"board": (1, 0, 38, 2), "focus": (1, 3, 38, 2),
                "record": (1, 6, 38, 2)}),
    (58, 14): ("M", 2, (),
               {"board": (1, 0, 27, 6), "capture": (1, 7, 27, 5),
                "focus": (30, 0, 27, 7), "record": (30, 8, 27, 4)}),
    (80, 12): ("S", 2, (),
               {"board": (1, 0, 38, 2), "capture": (1, 6, 38, 2),
                "focus": (41, 0, 38, 2), "record": (41, 6, 38, 2)}),
    (80, 13): ("M", 2, (),
               {"board": (1, 0, 38, 6), "capture": (1, 7, 38, 4),
                "focus": (41, 0, 38, 7), "record": (41, 8, 38, 3)}),
    (80, 24): ("M", 2, (),
               {"board": (1, 0, 38, 12), "capture": (1, 13, 38, 9),
                "focus": (41, 0, 38, 14), "record": (41, 15, 38, 7)}),
    (80, 26): ("M", 2, (),
               {"board": (1, 0, 38, 13), "capture": (1, 14, 38, 10),
                "focus": (41, 0, 38, 15), "record": (41, 16, 38, 8)}),
    (80, 27): ("L", 2, (),
               {"board": (1, 0, 38, 13), "capture": (1, 14, 38, 11),
                "focus": (41, 0, 38, 15), "record": (41, 16, 38, 8)}),
    (86, 24): ("M", 3, (),
               {"board": (1, 0, 26, 13), "capture": (57, 0, 26, 11),
                "focus": (29, 0, 26, 15), "record": (1, 14, 26, 8)}),
    (120, 34): ("L", 2, (),
                {"board": (1, 0, 58, 13), "capture": (1, 18, 58, 11),
                 "focus": (61, 0, 58, 15), "record": (61, 20, 58, 8)}),
    (160, 24): ("L", 4, (),
                {"board": (1, 0, 38, 13), "capture": (81, 0, 38, 11),
                 "focus": (41, 0, 38, 15), "record": (121, 0, 38, 8)}),
    (160, 44): ("L", 2, (),
                {"board": (1, 0, 78, 13), "capture": (1, 18, 78, 11),
                 "focus": (81, 0, 78, 15), "record": (81, 20, 78, 8)}),
}
CARD_W = {"board": "#tile-board", "focus": "#tile-focus",
          "capture": "#tile-capture", "record": "#tile-record"}


def _plain(markup: str) -> str:
    return re.sub(r"\[/?[^\]]*\]", "", markup)


def test_the_fixture_set_covers_every_shape_the_deck_can_take():
    """THE INPUT SET IS ITSELF AN ORACLE. Every law below quantifies over
    GOLDEN, so GOLDEN's completeness decides what those laws can see — and no
    mutation of the app can reveal a size the table never lists. The first draft
    of this batch's design assumed the deck was always one or two columns; a
    sweep found it is also three and four, and the whole layout plan was wrong.
    That is what an unguarded fixture list costs."""
    cols = {deck.plan(w, h)[0][0] for w, h in GOLDEN}
    assert cols == {1, 2, 3, 4}, f"column counts covered: {sorted(cols)}"
    assert {t for t, _c, _s, _g in GOLDEN.values()} == {"S", "M", "L"}
    assert {len(s) for _t, _c, s, _g in GOLDEN.values()} == {0, 1, 2}
    # and the declared cols must be the real cols, or the table is decorative
    for (w, h), (_t, c, _s, _g) in GOLDEN.items():
        assert deck.plan(w, h)[0][0] == c, f"{w}x{h} declared cols={c}"


@pytest.mark.parametrize("size", sorted(GOLDEN))
async def test_every_card_sits_exactly_where_the_seat_put_it(size):
    """AT-01. The cards are placed absolutely from `deck.plan`/`deck_rows`, so a
    card's region on screen IS the seat's arithmetic. Screen y is one below the
    deck's own y because the ribbon owns the top row."""
    tier, _cols, shed, cards = GOLDEN[size]
    app = Deck()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(*size)
        await pilot.pause()
        assert deck.tier(*size) == tier
        for card, wid in CARD_W.items():
            w = app.query_one(wid)
            if card in shed:
                assert w.display is False, f"{card} was shed but still shown"
                continue
            x, y, cw, ch = cards[card]
            r = w.region
            assert (r.x, r.y, r.width, r.height) == (x, y + 1, cw, ch), (
                f"{card} at {size}: seat says {(x, y + 1, cw, ch)}, "
                f"the app put it at {(r.x, r.y, r.width, r.height)}")


@pytest.mark.parametrize("size", [(40, 12), (80, 24), (120, 34), (160, 24)])
async def test_the_chrome_takes_exactly_the_two_rows_it_declares(size):
    """AT-01b. `deck.CHROME` is the number `deck_rows` budgets against. If the
    app spends a different number of rows on chrome, every card height is wrong
    by that difference and nothing else would say so."""
    app = Deck()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(*size)
        await pilot.pause()
        ribbon = app.query_one("#ribbon").region
        bar = app.query_one("#hints").region
        body = app.query_one("#strip").region
        assert ribbon.y == 0 and ribbon.height == 1
        assert bar.height == 1 and bar.y == size[1] - 1
        assert body.height == size[1] - deck.CHROME
        assert ribbon.height + bar.height == deck.CHROME


async def test_the_deck_follows_the_seat_rather_than_agreeing_with_it(monkeypatch):
    """AT-01c — THE PERTURBATION ORACLE, and the only law here that can tell
    'the app reads the seat' apart from 'the app happens to agree with the seat'.
    A hard-coded layout that matched every golden above would pass all of them
    and fail this one.

    Give every card one more row than the seat really allots and the rendered
    cards must all grow by exactly one."""
    size = (120, 34)
    real = deck.deck_rows

    app = Deck()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        before = {c: app.query_one(w).region.height for c, w in CARD_W.items()}

        monkeypatch.setattr(deck, "deck_rows",
                            lambda *a, **k: {c: r + 1 for c, r in real(*a, **k).items()})
        app._paint()
        await pilot.pause()
        after = {c: app.query_one(w).region.height for c, w in CARD_W.items()}

    assert before == {"board": 13, "focus": 15, "capture": 11, "record": 8}, before
    for card in CARD_W:
        assert after[card] == before[card] + 1, (
            f"{card} ignored the seat: {before[card]} -> {after[card]}")


async def test_a_shed_card_is_named_in_words_when_the_bar_has_the_room():
    """AT-03. Nothing the operator could act on leaves the screen silently. At
    40x12 the deck sheds `capture` and the key bar says so, in the word."""
    app = Deck()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(40, 12)
        await pilot.pause()
        bar = _plain(str(app.query_one("#hints").render()))
        assert hints.SHED_MARK in bar, bar
        assert "capture" in bar, f"shed but not named: {bar!r}"
        w = app.query_one(CARD_W["capture"])
        assert w.display is False
        assert w in app.query(".tile"), "a shed card must keep its place"


@pytest.mark.parametrize("size,shed", [((40, 12), ["capture"]),
                                       ((30, 8), ["capture", "record"])])
async def test_a_shed_card_is_always_marked_in_the_ribbon(size, shed):
    """AT-03b — the half that holds at EVERY size, and the reason the law needs
    two halves.

    At 30x8 the bar has 28 cells. `hidden capture record` is 22 and
    `esc strip · q quit` is 18; in the day-close they genuinely do not both fit,
    and the way out has to win. So the words are the affordable half and the
    ribbon carries the half that is always affordable: four letters, one mark.
    Loss is still visible — it is just spelled shorter."""
    app = Deck()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(*size)
        await pilot.pause()
        ribbon = _plain(str(app.query_one("#ribbon-cards").render()))
        bar = _plain(str(app.query_one("#hints").render()))
        for card in shed:
            key = {"board": "B", "focus": "F",
                   "capture": "C", "record": "M"}[card]
            assert key + RIBBON_SHED in ribbon, (
                f"{card} was shed unmarked: {ribbon!r}")
            assert app.query_one(CARD_W[card]).display is False
        for card in set(CARD_W) - set(shed):
            key = {"board": "B", "focus": "F",
                   "capture": "C", "record": "M"}[card]
            assert key + RIBBON_SHED not in ribbon, (
                f"{card} is on the deck but marked shed: {ribbon!r}")
        assert len(bar) <= size[0] - 2, f"the bar overflows: {len(bar)} cols"


async def test_nothing_is_announced_when_nothing_was_shed():
    """AT-03, the negative half. It has to key on the MARK, not on the word
    `capture` — at 80x24 the ordinary legend already reads `c capture`, so
    asserting the bare name absent would fail on a correct app."""
    app = Deck()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        bar = _plain(str(app.query_one("#hints").render()))
        assert "capture" in bar               # the ordinary hint, not a shed mark
        assert hints.SHED_MARK not in bar, bar
        for wid in CARD_W.values():
            assert app.query_one(wid).display is True


def test_the_shed_argument_changes_nothing_when_nothing_is_shed():
    """The default has to be inert, or every existing hint-bar law is testing a
    different function than the one that ships."""
    for mode in ("strip", "board", "focus", "capture", "record", "close"):
        for w in range(30, 121):
            assert hints.render(mode, w) == hints.render(mode, w, shed=())
            assert hints.visible_width(mode, w) == hints.visible_width(
                mode, w, shed=())


@pytest.mark.parametrize("size", [(40, 12), (30, 8)])
async def test_the_day_close_keeps_its_way_out_at_the_sizes_that_shed(size):
    """AT-06. The shed announcement takes cells from the same bar that carries
    `esc`, and it takes them at exactly the sizes where the bar is tightest. A
    day-close with no advertised exit is a room with the door painted over."""
    app = Deck()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(*size)
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert app.mode == "close"
        bar = _plain(str(app.query_one("#hints").render()))
        assert "esc" in bar, f"no way out advertised at {size}: {bar!r}"
        assert "CLOSE" in str(app.query_one("#stage-body").render()).upper()
        await pilot.press("escape")
        await pilot.pause()
        assert app.mode == "strip"


def test_the_seat_is_sane_at_every_size_the_deck_can_be_asked_for():
    """AT-04. Swept over the pure seat rather than the app: 10 000+ pilot boots
    is not a test suite, and the invariants below are structural, not visual.

    The subject is `desk.app.seats` — app code, not `deck.py` — so this is not
    the deck agreeing with itself."""
    order = set(deck.DECK_ORDER)
    bad = []
    for w in range(1, 241, 3):
        for h in range(1, 81):
            tname, seat, shown, shed = seats(w, h)
            if set(shown) | set(shed) != order:
                bad.append((w, h, "a card vanished"))
            if set(shown) & set(shed):
                bad.append((w, h, "a card was both shown and shed"))
            for card, (x, y, cw, ch) in seat.items():
                if cw < 1 or ch < 1:
                    bad.append((w, h, f"{card} sized {cw}x{ch}"))
                if x < 0 or y < 0:
                    bad.append((w, h, f"{card} placed at {x},{y}"))
            # no two cards may occupy the same cell
            boxes = list(seat.items())
            for i, (c1, (x1, y1, w1, h1)) in enumerate(boxes):
                for c2, (x2, y2, w2, h2) in boxes[i + 1:]:
                    if (x1 < x2 + w2 and x2 < x1 + w1
                            and y1 < y2 + h2 and y2 < y1 + h1):
                        bad.append((w, h, f"{c1} overlaps {c2}"))
    assert not bad, bad[:8]


def test_a_window_too_small_to_seat_anything_still_answers():
    """`deck.plan`'s degenerate branch returns `w - 2` with no floor under it,
    so a 0x0 window — which is what the app reports before its first layout —
    yields a card width of -2. A negative width is a negative slice inside a
    renderer, and the renderer it reaches first recurses until it dies."""
    for w, h in [(0, 0), (1, 1), (2, 3), (5, 4), (-4, -4)]:
        _t, seat, shown, shed = seats(w, h)
        assert shown, f"{w}x{h} seated nothing at all"
        for card, (x, y, cw, ch) in seat.items():
            assert cw >= 1 and ch >= 1, f"{w}x{h}: {card} sized {cw}x{ch}"
            assert x >= 0 and y >= 0
