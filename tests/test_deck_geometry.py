"""The deck's geometry — the laws the S/M/L ladder has to keep.

These are layout laws, so they are checked as arithmetic over the seat every
renderer will read. Nothing here renders anything; that is the point — a layout
bug found by squinting at a screenshot is a layout bug found late.
"""
from __future__ import annotations

from desk import deck

SIZES = {"S": (40, 12), "M": (80, 24), "L": (120, 34)}


def test_the_rename_moved_no_threshold():
    """THE RECEIPT. An earlier pass measured card_h < 5 and >= 12 as the two
    breakpoints and called the bands XS/S/M. This one claims it moved the NAMES
    and not the arithmetic. A claim in a comment is not evidence, so the two
    numbers and the three sizes they label are asserted."""
    assert (deck.TIER_M_MIN_H, deck.TIER_L_MIN_H) == (5, 12)
    for name, (w, h) in SIZES.items():
        assert deck.tier(w, h) == name, f"{w}x{h} labelled {deck.tier(w, h)}"


def test_a_wider_window_never_buys_a_smaller_deck():
    """Monotonicity is what makes a resize feel like a resize instead of a
    reshuffle. Dragging a window wider must never take a card's detail away."""
    rank = {"S": 1, "M": 2, "L": 3}
    bad = []
    for h in range(12, 41, 2):
        prev = 0
        for w in range(40, 161, 4):
            r = rank[deck.tier(w, h)]
            if r < prev:
                bad.append(f"{w}x{h} dropped a tier")
            prev = max(prev, r)
    assert not bad, bad[:5]


def test_forty_by_twelve_cannot_seat_four_cards():
    """The honest floor. `deck_grid` returning None is a real answer, not a
    failure — and it is what forces `plan` to shed rather than to squeeze four
    cards into two rows each and call it a deck."""
    assert deck.deck_grid(40, 12, 4) is None


def test_a_shed_card_is_shed_and_a_pinned_card_never_is():
    """Nothing the user could act on leaves the screen silently, and the card
    that is actually DOING something is the last thing to go. A deck that sheds
    a running timer to make room for an idle capture box has its priorities
    backwards."""
    _g, shown, shed = deck.plan(40, 12)
    assert shed, "40x12 shed nothing — the tier is over-promising"
    assert set(shown) | set(shed) == set(deck.DECK_ORDER)   # nothing vanishes
    first = shed[0]
    # Pin exactly the card that would otherwise go first: a weaker check (pin
    # something that was never at risk) passes even when `pinned` is ignored
    # outright, which is how the first draft of this law missed that mutant.
    _g, shown, shed = deck.plan(40, 12, pinned={first})
    assert first not in shed, f"{first} was pinned and shed anyway: {shed}"
    assert shed, "pinning one card must move the shed, not cancel it"
    assert set(shown) | set(shed) == set(deck.DECK_ORDER)


def test_cards_are_weighted_by_what_they_know():
    """A deck whose four cards share one weight vector is allocating by symmetry
    instead of by information. Focus knows a fire, a clock and a set; Record
    knows a level and a state. They are not the same size of thing."""
    assert len(set(deck.CARD_WEIGHT.values())) > 1, deck.CARD_WEIGHT


def test_no_card_is_inflated_past_what_it_can_say():
    """The surplus pass hands leftover rows to each card's variable block, and
    this is the stop on it. A card with nothing more to say gets nothing —
    otherwise the deck fills holes with stretched information, which reads worse
    than the hole did."""
    w, h = SIZES["L"]
    grid, shown, _shed = deck.plan(w, h)
    got = deck.deck_rows(shown, grid[0], h - deck.CHROME, "L")
    for c, r in got.items():
        cap = (deck.CARD_WEIGHT[c] - deck.FIELD_ROWS[c][deck.VARIABLE_FIELD[c]]
               + deck.FIELD_MAX[c])
        assert r <= cap, f"{c}: {r} rows > ceiling {cap}"


def test_a_variable_block_never_renders_with_zero_rows():
    """The defect this guards is invisible from the outside: a card that draws
    its header, its rule and its total with every entry sliced away still LOOKS
    like a card. Sizing the block against the declared table instead of a magic
    constant makes zero unreachable."""
    for card in deck.CARD_FIELDS:
        idx = deck.CARD_FIELDS[card].index(deck.VARIABLE_FIELD[card])
        for h in range(deck.CARD_MIN_H, 20):
            want = deck.deck_want(card, h, "L")
            if want > idx:
                assert deck.room(h, card, idx, want) >= 1, f"{card} at h={h}"


def test_a_hero_cannot_starve_the_fields_behind_it():
    """THE THIRD TABLE'S REASON. Costed against the APPETITE, Focus's 9-row
    ember consumed the budget and the walk stopped there: the dots, the keys and
    the set line were unreachable at every height a card ever gets. Costed
    against the FLOOR, the walk gets past the hero and the surplus comes back to
    it. This test fails if FIELD_MIN is ever collapsed back into FIELD_ROWS."""
    h = deck.deck_grid(*SIZES["M"])[3]                # the real M card height
    n = len(deck.CARD_FIELDS["focus"])
    assert deck.deck_want("focus", h, "M") == n, (
        f"at the M height ({h} rows) Focus still cannot reach its own key line")

    def appetite_walk(card, height):                  # the same walk, mis-costed
        cost = got = 0
        for f in deck.CARD_FIELDS[card]:
            cost += deck.FIELD_ROWS[card][f]
            if cost > height:
                break
            got += 1
        return got

    assert appetite_walk("focus", h) < n, (
        "the appetite table no longer starves the card at the M height — the "
        "floor table has stopped being load-bearing and this law is vacuous")


def test_every_card_keeps_a_floor_of_rows():
    """No card is allowed to be allocated below the point where it can draw
    anything, at any size the deck admits."""
    for name, (w, h) in SIZES.items():
        grid, shown, _shed = deck.plan(w, h)
        got = deck.deck_rows(shown, grid[0], h - deck.CHROME, name)
        assert got, name
        for c, r in got.items():
            assert r >= deck.CARD_MIN_H, f"{name}: {c} got {r} rows"


def test_the_deck_is_never_built_out_of_the_reference_model():
    """`_tui_synthesis` is a MODEL. Importing it at runtime would make a
    scratch directory a dependency of the shipped app."""
    import pathlib
    src = pathlib.Path(deck.__file__).parent
    for p in src.glob("*.py"):
        assert "_tui_synthesis" not in p.read_text(encoding="utf-8"), p.name
