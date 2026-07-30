# 02 — Cross-agent review · dispositions

Three reviewers (architect · qa · security) ran in parallel against `01-requirements.md` +
`01b-design.md`. **14 blockers**, 20 majors. Every finding below was *executed*, not argued.

**Gate verdict: `iterate` on Phase 1 — the spec is amended, then Phase 3 proceeds.**

## Blockers — dispositioned

| # | finding | disposition |
|---|---|---|
| A-F1 / Q-3 / Q-4 | **At tier S the spec is unsatisfiable.** `deck_want` short-circuits at S returning `TIER_PREFIX["S"]==2` — a **row budget**, not a field count. `CARD_FIELDS["focus"][:2] == ("head","ember")` and `ember`'s floor is 4 rows inside a 2-row card. AT-02 asserted the opposite. | **ACCEPTED.** New **LLR-02.0**: at S the card paints its *glance* form (head + `render_tile`'s line) and `render_card` is **not called** — matching `desk_final.py:1755-1759` (`card_glance`) and PROPOSAL §5.1. `deck.py` is NOT modified (qa's alternative fix would break `test_deck_geometry.py`). |
| S-F1 | **`deck.plan` returns negative `cw`** (`deck.py:220`, `w-2` unclamped): `plan(0,0)`→`-2`. Fed to `board._emit` → **`RecursionError`** via the negative slice at `board.py:252`. | **ACCEPTED.** Clamped at the app boundary in `_seats` (`deck.py` stays frozen), plus a defensive clamp in the renderers. Sweep test over `w ∈ -2..200`. |
| A-F3 | **Deck and `#stage` cannot both hold the body.** A deck of `h-2` leaves `#stage` zero rows — and `test_smoke.py:40-42` is true at height 0, so 230 tests stay green. | **ACCEPTED.** The deck container is `display=False` while `mode != "strip"`. This *is* the doctrine: "`enter` gives one card the whole window". |
| A-F2 | **`per = slack*2//3//gaps` divides by zero** whenever a column holds one card — every column at cols=4. | **ACCEPTED.** `per = 0 if gaps == 0 else …`. |
| A-F4 | **A line wider than `cw` wraps and silently deletes the lines after it.** Measured on textual 8.2.8. | **ACCEPTED.** Cards get `text-wrap: nowrap; overflow: hidden`; every emitted line clamped to `cw`. |
| A-F5 | `want` and `tname` had no provenance; `deck_rows` needs `tname`, which no LLR produced. | **ACCEPTED.** `_seats` computes `tname = deck.tier(w,h)`, `rows = deck_rows(...)`, `want = deck_want(card, rows[card], tname)`. |
| A-F13 | `self.size` is `(0,0)` at `on_mount` in production and **`run_test` can never reproduce it** (pilot pre-sets size). | **ACCEPTED.** `_seats` floors its inputs; a direct `_paint()` test at size 0 replaces the unreachable pilot case. |
| Q-6 | **The shed announcement is silently dropped at 30x8** — `hints.fit` sheds essentials from the front (`hints.py:78-81`), and 30x8 sheds *two* cards. The exact failure US-03 exists to prevent. | **ACCEPTED.** The shed segment is rendered **outside** `fit`, with its width reserved first, so it can never be dropped. |
| Q-7 | **The ember breath never reaches the card.** `render_card(..., phase=0)` has a default; `_tiles()` passes no phase. Frozen ember, 230 green — verbatim the defect `test_motion.py:88` warns about. | **ACCEPTED.** `phase=self._ticks` threaded; **AT-05** clones the pinned-clock idiom onto `#tile-focus`, with the stopped-timer negative half. |
| A-F14 / Q-13 | **The hue-ration law does not cover `render_card`.** The spy at `test_hue_ration.py:86-97` never calls it, so a direct `temp_hex` call leaves `seen <= RAMP_SEATS` **vacuously** true. | **ACCEPTED.** **AT-07** exercises `focus.render_card` under the same spy, with `assert seen` (the anti-vacuity clause). The law's `RAMP_SEATS` is **not** edited. |
| A-F6 / Q-1 | **AT-01's `cols=4` fixture is factually wrong** — `plan(160,44)` measures `cols=2`. The AT written to prevent a repeat of the Phase-0 error was blind to the widest column count. | **ACCEPTED.** Fixtures re-measured; `160x24` gives cols=4. A guard asserts the fixture set covers `{1,2,3,4}`. |
| Q-2 | **Nothing proved the seat *governs*.** "Independently recomputed" is an intention with no mechanism; if the test calls the app's own helper, every arithmetic error is invisible. | **ACCEPTED.** Three legs: golden literal regions + pilot `region` compare + **AT-01c, a perturbation oracle** (monkeypatch `deck.deck_rows` to return rows+1; every card's region height must move by exactly 1). |
| A-F18 / Q-5 | **AT-04 was a tautology** (`i % cols == i % cols`) and 10 317 pilot boots is infeasible. | **ACCEPTED.** Split: the sweep runs over the app's pure `_seats` (subject = app code, red pre-wiring because `_seats` did not exist); the pilot drives 12 sizes. |
| A-F15 | **The increment cut did not hold** — Inc 2 rewrote the panels but had no `app.py` to switch the call site, and AT-01's text clause could not go green at the end of Inc 1. | **ACCEPTED.** Re-cut: Inc 1 = geometry (glance body at every tier); Inc 2 = the card seats **+ `app.py`'s call-site switch**; AT-01c (text differs by tier) moves to Inc 2. |

## Majors folded

A-F7 (origin of `x`/`y` defined: container-relative, `x = 1 + gc*(cw+GUTTER)`) · A-F8 (slack rule
restated per-column, exact) · A-F10 (the ribbon widget named: `#ribbon` holding `#ribbon-cards`
+ the re-parented `#clock`) · A-F11 (the `desk.tcss` declarations to delete, enumerated) ·
A-F12 (degenerate floor) · A-F21 (styles written only when the seat changes) · Q-8 (`hints.SHED_MARK`
sentinel, so the negative clause is observable — the bare word `capture` is already in the
80x24 legend) · Q-10 (tier-threshold fixtures 80x12/13 and 80x26/27) · Q-11 (58x14, the narrowest M) ·
Q-12 (**AT-02d**: the focus head's run mark, both halves) · Q-16 (line-count **floor**, not only a ceiling) ·
Q-17 (**AT-06**: `d` keeps its `esc` exit at shed sizes) · S-F5 (`hearth_lines` gains a `rows`
parameter — it hardcodes 9 today) · S-F6 (`room` guarded by `idx < want`).

## Findings deliberately NOT actioned — reported instead

- **S-F3 · `record.py:293` and `:377-378` render unescaped external strings today.** The web-video
  title is network-sourced and attacker-controlled; under Textual's parser an injected
  `[@click=app.quit]` becomes a **live action span**. This is **pre-existing on `main`**, not
  introduced here. `CARD_FIELDS["record"]` is `("head","state","meter","auto","whisper")` — the
  title and the transcript preview are **not** among them, so the new card path does not widen
  the exposure. Out of scope per "touch nothing beyond the wiring"; **carried to the backlog as
  a HIGH**, with a card-seat test asserting the transcript never reaches the deck.
- **S-F4 · a hostile `board.json` title with embedded newlines / CJK breaks the row contract.**
  Real, pre-existing, and newly *consequential* under absolute placement. Mitigated **defensively**
  in this batch (lines clamped to `cw`, card `overflow: hidden`) rather than fixed at the trust
  boundary; the boundary fix is carried to the backlog.
- **S-F8 · quadratic ledger cost** (43 ms at 2 000 tasks, on a 1 s lane) — carried.
- **S-secrets · the board ledger becomes permanently visible at L**, exposing client project
  names during any screen share. Design consequence of the approved proposal, not a defect.
  **Surfaced to the operator** rather than silently accepted or silently redacted.
