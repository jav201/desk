# 01b — Phase 1 · HLR / LLR / AT · wiring the deck

**BLUF.** The deck is laid out by **absolute placement**: `_paint` asks `deck.plan` /
`deck_rows` for every card's `(x, y, w, h)` and writes it onto the widget's styles. This is
the strongest available form of D5 — the seat does not *advise* the layout, it *is* the
layout, so a test that compares a widget's `region` to the seat's arithmetic cannot be vacuous.

## The design correction that Phase 1 bought

The Phase-0 gate proposed two fixed column containers (`col0 = board+capture`,
`col1 = focus+record`) on my reasoning that `cols ∈ {1,2}`. **Executed, that reasoning was
false.** A sweep of 10 317 sizes found **8 038 mismatches**: `deck_grid` chooses `cols` from
`1..4`, and every value occurs:

| (cols, cards shown) | sizes |
|---|---|
| (1,1) 114 · (1,2) 114 · (1,3) 114 · (1,4) 1922 | |
| (2,2) 84 · (2,4) 3908 | |
| (3,3) 84 · (3,4) 2179 | |
| (4,4) 1798 | |

Any design with a fixed number of column containers is therefore wrong, and would have been
wrong in a way no existing test could see. Recorded as a **C-40 limb-2 catch**: the set was
derived from the rule (sweep every size) rather than from my model of the rule.

**Executed probe of the replacement** (`position: absolute` + `offset` + explicit `width`/
`height`, textual 8.2.8, headless `run_test(size=(80,24))`):

```
c0: want=(0,0,38,12)  got=(0,0,38,12)  OK
c1: want=(40,0,38,14) got=(40,0,38,14) OK
c2: want=(0,12,38,9)  got=(0,12,38,9)  OK
c3: want=(40,14,38,7) got=(40,14,38,7) OK
```

Four cards, four different heights, two columns — all placed exactly. `str(Static.render())`
still returns the content, so every existing tile assertion keeps working.

---

## Requirements

### HLR-01 — the deck is laid out by the geometry seat
*Traces to US-01.*
> The app **shall** derive every card's position and size for the current terminal size from
> `desk.deck`, and **shall not** encode any card position or size in `desk.tcss`.

- **LLR-01.1** `Deck._paint` **shall** call `deck.plan(w, h, pinned=…)` and `deck.deck_rows`
  and place each card widget at the resulting `(x, y, cw, rows)` via `styles.offset`,
  `styles.width`, `styles.height`.
  *Touched symbols (C-26): `#tile-board`, `#tile-focus`, `#tile-capture`, `#tile-record`,
  `#strip`, `#clock`, `.tile`.*
- **LLR-01.2** Column `gc` **shall** hold the cards at indices `i` of `shown` where
  `i % cols == gc`, matching `deck_rows`' own partition; `x = 1 + gc * (cw + GUTTER)`.
- **LLR-01.3** Inter-card slack **shall** follow the approved rule — base `VGAP` when it
  fits, then two thirds of the remaining slack distributed between cards, capped at 4 rows,
  the rest left as bottom margin.
- **LLR-01.4** `Deck.on_resize` **shall** repaint, so a resize re-seats the deck.
- **LLR-01.5** The chrome **shall** occupy exactly `deck.CHROME` (2) rows: a 1-row ribbon
  docked top and the 1-row key bar docked bottom; the deck body gets the remaining `h - 2`.

### HLR-02 — each card renders the form its seat pays for
*Traces to US-02.*
> Each panel module **shall** expose a `render_card` seat that draws exactly the prefix of
> its declared fields that `deck.deck_want` pays for, and **shall** renounce a field whole
> rather than truncate it.

- **LLR-02.1** `board.render_card(data, w, h, want, *, beat=False, today=None)` **shall**
  emit the first `want` of `("head","now","horizon","ledger","detail")`, sizing `ledger`
  by `deck.room(h, "board", 3, want)`.
- **LLR-02.2** `focus.render_card(pomo, w, h, want, *, beat=False, phase=0)` **shall** emit
  the first `want` of `("head","ember","dots","keys","set")`, sizing `ember` by
  `deck.room(h, "focus", 1, want)`, and **shall** obtain every fire-ramp colour through
  `focus.hearth_lines` — never by calling `focus.temp_hex` itself *(forced by P-9)*.
- **LLR-02.3** `capture.render_card(prompt, saved, w, h, want)` — first `want` of
  `("head","prompt","input","cycle","dest")`, `cycle` sized by `deck.room(h,"capture",3,want)`.
- **LLR-02.4** `record.render_card(state, seconds, level, …, w, h, want, phase=0)` — first
  `want` of `("head","state","meter","auto","whisper")`, `meter` sized by
  `deck.room(h,"record",2,want)`.
- **LLR-02.5** The focus card's `head` **shall** carry the timer's run mark and remaining
  time *(forced by P-10: `tests/test_focus.py:65` asserts `▸` in `#tile-focus` at tier M)*.
- **LLR-02.6** `render_tile` and `render_body` **shall** keep their current signatures and
  behaviour; `render_card` is additive *(D6)*.

### HLR-03 — a shed card is named
*Traces to US-03.*
> When the deck sheds a card, the app **shall** name that card in the key bar and mark it in
> the ribbon; a shed card's widget **shall** remain in the widget tree.

- **LLR-03.1** `hints.render(mode, width, shed=())` and `hints.visible_width(mode, width,
  shed=())` **shall** accept the shed set and emit one never-dropped entry naming each shed
  card. Default `()` preserves today's output exactly.
- **LLR-03.2** A shed card's widget **shall** be `display=False`, never removed
  *(forced by P-8: `tests/test_smoke.py:40-41` queries `#tile-capture` / `#tile-record` at
  40x12 and 30x8, where those cards are shed)*.
- **LLR-03.3** `#clock` **shall** be hidden below 58 cells and remain in the tree *(D7, §5.1)*.

---

## Acceptance tests (Layer B, black-box)

| id | story | drives | asserts |
|---|---|---|---|
| **AT-01** | US-01 | real app via `run_test`, resized to 40x12 / 80x24 / 120x34 / 86x24 (cols=3) / 160x44 (cols=4 band) | every visible card's `widget.region` equals the `(x,y,w,h)` independently recomputed from `deck.plan`+`deck_rows`; and the three tiers do not render identical card text |
| **AT-01b** | US-01 | the same pilot | the chrome occupies exactly `deck.CHROME` rows: ribbon at y=0 h=1, `#hints` at the bottom h=1, deck body h = `size.height - 2` |
| **AT-02** | US-02 | real app at S vs L | the focus card at S contains **no** carved-ember glyph row and at L does; no field renders as a truncated fragment (a field is present in full or absent) |
| **AT-02b** | US-02 | `render_card` directly, swept over every `(h, want)` the seat can produce | line count never exceeds `h`; the variable block never renders with zero rows |
| **AT-03** | US-03 | real app at 40x12 then 80x24 | at 40x12 the `#hints` plain text contains `capture` **and** `#tile-capture` is still queryable with `display is False`; at 80x24 no shed announcement appears |
| **AT-04** | all | the layout invariant | sweep every size 20..200 x 4..60: the column partition the app computes equals `i % cols` for `deck_rows` — the check that refuted the Phase-0 design |

**Counterfactual obligation (C-40):** each AT above must be shown RED on the pre-wiring tree
(AT-01/01b/03 fail because the seat is never consulted; AT-02/02b fail because `render_card`
does not exist). Captured before the completing edit, per increment.

---

## Increment plan (re-cut per C-21 after the D1 ruling + the README addition)

| inc | files | ATs |
|---|---|---|
| **1** | `desk/app.py`, `desk/desk.tcss`, `desk/hints.py`, `tests/test_deck_wiring.py` | AT-01, AT-01b, AT-03, AT-04 |
| **2** | `desk/board.py`, `desk/focus.py`, `desk/capture.py`, `desk/record.py`, `tests/test_card_seats.py` | AT-02, AT-02b |
| **3** | `README.md` | — (documentation; operator-mandated addition) |

Total **10 files** against the operator's lifted cap.

## Deviation, declared

The brief specified a `render_card(size_tier)` seat. **The seat takes `(w, h, want)` instead.**
A tier alone cannot size a card: measured at tier M, `focus` is allotted 14 rows and `record`
7 — the same tier, different cards, different heights. `want` is the tier's expression, and
`deck.deck_want(card, h, tier)` is what produces it. Passing the tier alone would force each
renderer to re-derive its own height and re-introduce the magic constants `deck.room` exists
to eliminate.
