"""The deck's geometry — how four sovereign cards share a window.

Pure arithmetic and declared tables. No widgets, no markup, no Textual import,
so the layout can be reasoned about and tested without running an app — the same
rule the panel modules already follow.

THREE SIZES, and the arithmetic that names them was measured before the names
were chosen:

    S   40x12   card_h < 5    the glance deck — every card shows its strip line
    M   80x24   card_h = 10   expanded cards, a prefix of each card's fields
    L  120x34   card_h >= 12  the full deck, every declared field seated

THE STAGE IS NOT A SIZE. `enter` gives one card the whole window. It is not
called L, and the distinction is not pedantry: a size name promises that a wide
enough window arrives there on its own, and this one never does. L is the
largest deck AND the size at which entering the stage starts to be worth it.
"""
from __future__ import annotations

N = 4
CARD_MIN, GUTTER, VGAP = 26, 2, 1
ASPECT = 3.25                    # cards read as cards, not as columns or bands
CHROME = 2                       # the ribbon (1) + the key bar (1)
DECK_ORDER = ("board", "focus", "capture", "record")

# The order cards are SHED in when the window cannot seat them all. Board goes
# last because it is the only card that knows about anything outside desk.
SHED = ("capture", "record", "focus", "board")


def deck_grid(w: int, h: int, n: int = N):
    """(cols, rows, card_w, card_h) for `n` cards in a w x h window, or None
    when nothing legal fits — which is a real answer, not a failure: 40x12
    genuinely cannot seat four cards, and `plan` is what decides who leaves."""
    cmax = max(1, min(n, (w - 2) // (CARD_MIN + GUTTER)))
    body = h - CHROME
    best = None
    for c in range(1, cmax + 1):
        rows = -(-n // c)
        cw = (w - 2 - (c - 1) * GUTTER) // c
        ch = (body - (rows - 1) * VGAP) // rows
        if ch < 2:
            continue
        key = (abs(cw / ch - ASPECT), -c)              # a tie prefers MORE columns
        if best is None or key < best[0]:
            best = (key, (c, rows, cw, ch))
    return best[1] if best else None


TIER_S, TIER_M, TIER_L = "S", "M", "L"
TIER_M_MIN_H = 5                 # below this no card can carry a drawn figure
TIER_L_MIN_H = 12                # at this height a card seats its full weight


def tier(w: int, h: int, n: int = N) -> str:
    g = deck_grid(w, h, n)
    if not g or g[3] < TIER_M_MIN_H:
        return TIER_S
    return TIER_L if g[3] >= TIER_L_MIN_H else TIER_M


# ---- the drop orders --------------------------------------------------------
# CARD_FIELDS is the ORDER: the prefix that survives, first field first.
# FIELD_ROWS is the APPETITE: what a field costs when the room is there.
# FIELD_MIN  is the FLOOR: its smallest legible form, and what decides how many
#            fields fit — costing against the appetite starves a card behind its
#            own hero. Focus's 9-row ember ate the whole budget, so the dots, the
#            keys and the set line were never reached. A hero that starves its
#            own card's legend is a hero nobody can operate.
CARD_FIELDS = {
    "board":   ("head", "now",    "horizon", "ledger", "detail"),
    "focus":   ("head", "ember",  "dots",    "keys",   "set"),
    "capture": ("head", "prompt", "input",   "cycle",  "dest"),
    "record":  ("head", "state",  "meter",   "auto",   "whisper"),
}
FIELD_ROWS = {
    "board":   {"head": 1, "now": 2, "horizon": 3, "ledger": 4, "detail": 1},
    "focus":   {"head": 1, "ember": 9, "dots": 1, "keys": 1, "set": 1},
    "capture": {"head": 1, "prompt": 1, "input": 2, "cycle": 4, "dest": 1},
    "record":  {"head": 1, "state": 1, "meter": 3, "auto": 1, "whisper": 1},
}
FIELD_MIN = {
    "board":   {"head": 1, "now": 2, "horizon": 3, "ledger": 1, "detail": 1},
    "focus":   {"head": 1, "ember": 4, "dots": 1, "keys": 1, "set": 1},
    "capture": {"head": 1, "prompt": 1, "input": 2, "cycle": 1, "dest": 1},
    "record":  {"head": 1, "state": 1, "meter": 2, "auto": 1, "whisper": 1},
}
# The one block per card that ABSORBS surplus rows. Everything else is fixed.
VARIABLE_FIELD = {"board": "ledger", "focus": "ember",
                  "capture": "cycle", "record": "meter"}
# ...and where that block stops being MORE INFORMATION and starts being the same
# information stretched. Measured one at a time:
#   board.ledger  6 — desk seats four projects plus Inbox; a seventh row is padding
#   focus.ember  11 — HEARTH_ROWS is 9; past ~11 the carved counter drowns in a
#                     column of solid fire and the field stops reading as a fire
#   capture.cycle 6 — there are exactly six real prompts to show
#   record.meter  4 — a VU plus an intake front; there is no third field
FIELD_MAX = {"board": 6, "focus": 11, "capture": 6, "record": 4}

CARD_WEIGHT = {c: sum(FIELD_ROWS[c].values()) for c in CARD_FIELDS}
GLANCE_ROWS, CARD_MIN_H = 2, 2
TIER_PREFIX = {TIER_S: 2, TIER_M: 5, TIER_L: 5}


def card_weight(card: str, tname: str) -> int:
    """At S every card renders its own strip line and nothing else, so the
    weights are equal there BY LAW rather than by coincidence."""
    return GLANCE_ROWS if tname == TIER_S else CARD_WEIGHT[card]


def deck_rows(shown, cols: int, body_h: int, tname: str) -> dict:
    """{card: rows}. SPACE IS EARNED BY INFORMATION — a card gets exactly what
    its declared fields cost, and the remainder stays deck ground."""
    out: dict[str, int] = {}
    for gc in range(cols):
        mine = [c for i, c in enumerate(shown) if i % cols == gc]
        if not mine:
            continue
        # SPACING YIELDS TO CONTENT. At S with four cards pinned, four cards at
        # two rows each is 8 and the body is 10 — but the three inter-card gaps
        # made it 11, so the last card drew its header and nothing else. A card
        # that appears and says nothing is worse than one that was shed and
        # named, and the gap is the only thing on the frame carrying no
        # information at all, so the gap goes first.
        want = [card_weight(c, tname) for c in mine]
        gaps = len(mine) - 1
        avail = body_h - gaps * VGAP
        if sum(want) > avail and sum(want) <= body_h:
            avail = body_h
        total = sum(want)
        if total <= avail:
            got = list(want)
        else:
            raw = [avail * x / total for x in want]
            got = [int(x) for x in raw]
            order = sorted(range(len(mine)), key=lambda i: (-(raw[i] - got[i]), i))
            for i in order[:max(0, avail - sum(got))]:
                got[i] += 1
            got = [max(CARD_MIN_H, g) for g in got]
            while sum(got) > avail and max(got) > CARD_MIN_H:
                got[max(range(len(got)), key=lambda i: (got[i], -i))] -= 1
        # THE SURPLUS. Read literally, "a card gets exactly what its fields
        # cost" leaves eleven blank rows across the bottom third of an L window,
        # which does not read as breathing room — it reads as a layout that
        # broke. The answer is not to inflate cards: every card declares one
        # block whose information genuinely scales with rows (a taller ember has
        # more vertical precision; more bars are more projects). Surplus goes
        # there, round-robin, capped. A card with nothing more to say still gets
        # nothing.
        if tname != TIER_S:
            cap = [card_weight(c, tname) - FIELD_ROWS[c][VARIABLE_FIELD[c]]
                   + FIELD_MAX[c] for c in mine]
            guard = 0
            while sum(got) < avail and any(g < k for g, k in zip(got, cap)):
                guard += 1
                if guard > avail * len(mine) + 8:      # bounded, always
                    break
                for i in range(len(mine)):
                    if got[i] < cap[i] and sum(got) < avail:
                        got[i] += 1
        for c, gh in zip(mine, got):
            out[c] = gh
    return out


def deck_want(card: str, h: int, tname: str) -> int:
    """How many DECLARED fields `h` rows can pay for — the surviving prefix.
    Costed against FIELD_MIN, never the appetite."""
    if tname == TIER_S:
        return TIER_PREFIX[tname]
    cost = want = 0
    for f in CARD_FIELDS[card]:
        c = FIELD_MIN[card][f]
        if cost + c > h:
            break
        cost += c
        want += 1
    return max(1, want)


def field_cost(card: str, upto: int, table=None) -> int:
    """Rows the first `upto` declared fields cost, so a renderer can size a
    variable block against what its later fields reserved rather than against a
    magic constant."""
    tbl = table or FIELD_MIN
    return sum(tbl[card][f] for f in CARD_FIELDS[card][:upto])


def room(h: int, card: str, idx: int, want: int) -> int:
    """Rows the variable block at declared-field index `idx` may spend: the
    card's height, less what came before, less what the fields after it — the
    ones this tier will actually draw — reserved at their FLOOR.

    Sizing these blocks against a constant like `h - 4` is how a card renders a
    header and a total with every entry sliced away and no test able to see it.
    A block sized against the declared table cannot silently reach zero."""
    before = field_cost(card, idx)
    after = sum(FIELD_MIN[card][f] for f in CARD_FIELDS[card][idx + 1:want])
    return max(0, h - before - after)


def plan(w: int, h: int, cards=DECK_ORDER, pinned=()):
    """(grid, shown, shed). Shed from the front of SHED until the grid is legal.

    A shed card is the caller's problem to NAME — nothing the user could act on
    may leave the screen silently. Bounded: each pass drops one card from a
    finite list. A card is `pinned` when it is live (a running timer, a
    recording) or carrying something overdue, and a pinned card is never shed."""
    shown, shed = list(cards), []
    for _ in range(len(shown)):
        g = deck_grid(w, h, len(shown))
        if g:
            return g, shown, shed
        victim = next((c for c in SHED if c in shown and c not in pinned), None)
        if victim is None or len(shown) <= 1:
            break
        shown.remove(victim)
        shed.append(victim)
    return (1, len(shown), w - 2,
            max(2, (h - CHROME) // max(1, len(shown)))), shown, shed
