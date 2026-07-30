# 01 — Requirements · 2026-07-30-batch-01 · wiring the deck

**BLUF.** The geometry seat is correct and unused. Wiring it is not a port of the approved
reference implementation: the reference paints the whole deck into **one** `Static`, and the
live app's 230 tests pin **six** widget ids across six files. The wiring must therefore
*repurpose* the existing widgets rather than replace them — which turns out to match
`deck.py`'s own docstring ("THE STAGE IS NOT A SIZE"). Seven decisions (D1–D7) need a call.

---

## 2.6 — Story refinement (Definition of Ready)

### US-01 — the deck lays out for the window it is in — **READY**

*Who* the operator, at any terminal size desk is asked to live at.
*What* the resting deck seats its cards per `deck.plan(w,h)` / `deck_rows` / `deck_want`,
so a resize changes **what is shown**, not only how it is clipped.
*Why* the seat exists, is tested, and governs nothing; today every size renders the same
one-line strip.
*Out of scope* the stage (`enter` / `b`,`f`,`c`,`m`,`d`) remains a MODE, not a size.

**Black-box AC (→ AT-01):** driving the real app to 40x12, 80x24 and 120x34 and reading the
rendered card widgets, the number of seated cards and each card's row count equal what
`deck.plan`/`deck_rows` return for that size, and the three sizes do not render identically.

### US-02 — each card renders its S / M / L form — **READY**

*Who* the operator.
*What* each panel gains a `render_card` seat that draws the prefix of its declared fields
that `deck_want` pays for: S = the glance line, M = expanded, L = every declared field.
*Why* card sovereignty — each card keeps its own idiom; only the chrome is shared.
*Out of scope* changing any panel's existing `render_tile` / `render_body` contract.

**Black-box AC (→ AT-02):** at S the focus card draws no carved ember; at L it does; a field
that does not fit is **absent entirely**, never a truncated fragment of itself.

### US-03 — a shed card is named — **READY**

*Who* the operator at S, where the deck cannot seat four cards.
*What* the key bar names the shed card(s).
*Why* nothing actionable may leave the screen silently. The backlog records AC-4.1 as
**half-met**: the shedding is right, the announcement is missing.

**Black-box AC (→ AT-03):** at 40x12 `capture` is shed and the string rendered by `#hints`
names it; at 80x24 nothing is shed and the key bar carries no shed announcement.

---

## 2.7 — Premise table (C-43)

Every premise the brief and the canon assert, executed against disk. **Two are FALSE.**

| # | premise | tier | verdict | executed evidence | disposition |
|---|---|---|---|---|---|
| P-1 | The app class is `DeskApp` and its `compose` is the paint path. | premise | ❌ **FALSE** | `desk/app.py:42` — `class Deck(App):`. There is no `DeskApp` in the tree. | Corrected: the class is `Deck`, and it **name-collides with the `deck.py` module**. Both will be in scope in `app.py`; the module is imported as `from . import deck` and referenced `deck.plan(...)`, the class stays `Deck`. Renaming the class is out of scope (11 test files import it). |
| P-2 | `desk/deck.py` is imported by nothing. | premise | ✅ TRUE | `grep -rn` over `desk/ tests/`: the only importer is `tests/test_deck_geometry.py:9`. No file in `desk/` references it. | The gate is real. |
| P-3 | 230 tests exist and pass on `main` @ `4dc7ed2`. | premise | ✅ TRUE | `python -m pytest -q` → `230 passed in 20.31s`, exit 0. | Baseline for the ledger. |
| P-4 | `_tui_synthesis/desk_final.py` is the reference for the deck rendering, portable to the app. | hypothesis | ❌ **FALSE as stated** | `desk_final.py:2310-2311` — `compose` yields exactly **one** widget, `Static(id="canvas")`; zero `Horizontal`/`Vertical`/`Grid` in 2355 lines; `:2322-2328` `paint()` writes the whole frame into it. The live app's tests pin `#stage-body`, `#tile-board/-focus/-capture/-record`, `#clock`, `#hints`. | The reference is portable as the **arithmetic and the field-prefix contract**, not as the widget architecture. See **D1**. |
| P-5 | The reference's key bar names the shed card. | premise | ❌ FALSE | `desk_final.py:1833` — `segs.append((kit["alert"], ..., f"  +{len(shed)}"))`. It emits a **count**, not a name. Its own obligations table (`:273-275`) claims otherwise. | US-03 must build the naming; it cannot be copied. Matches the backlog's "half-met". |
| P-6 | Opposite-sign column pairing makes the breath mean invariant. | axiom (refuted) | ❌ FALSE | Stated refuted by measurement (0.38 vs 0.17 dot-rows drift); mainline already dropped it. | **Do not reintroduce.** No pairing in this batch. |
| P-7 | `run_test()` drives the app at a size that exercises the deck. | premise | ✅ TRUE, and consequential | `inspect.signature(App.run_test)` → `size: tuple[int,int]|None = (80, 24)`. `deck.tier(80,24)` → **`M`**. | **Every** existing tile assertion runs at tier M, not S. Drives D3. |
| P-8 | All four cards are seated at every size the smoke test drives. | premise | ❌ FALSE | `deck.plan(40,12)` → shed `['capture']`; `deck.plan(30,8)` → shed `['capture','record']`. `tests/test_smoke.py:40-41` queries `#tile-capture` and `#tile-record` at **both** those sizes. | **A shed card's widget must stay in the tree** (`display=False`), never `remove()`. See **D2**. |
| P-9 | Adding `render_card` to `focus.py` is free. | premise | ❌ FALSE | `tests/test_hue_ration.py:73` `RAMP_SEATS = {"hearth_lines","render_tile"}`; `:86-91` monkeypatches `focus.temp_hex` with a spy reading `inspect.stack()[1].function`; `:96` asserts `seen <= RAMP_SEATS`. | `focus.render_card` must route all fire-ramp colour **through `hearth_lines`**. Editing the law is a design change, not a fixup. See **D4**. |
| P-10 | `#tile-focus` shows `▸` when the timer runs. | premise | ✅ TRUE today, ❌ breaks under naive wiring | `focus.render_tile(running)` → `'[#45c4ff]▸ 25:00[/]  [dim]○○○○○[/dim]'`. `tests/test_focus.py:65` asserts `"▸" in tile` at (80,24) = tier **M**, where the card's declared fields are head/ember/dots/keys/set — **none of which emits `▸`**. | The focus card's **head** must carry the run mark. See **D3**. |
| P-11 | `#tile-board` shows the current task at M. | premise | ✅ TRUE (path exists) | `board.current_doing(SAMPLE)` → `t2` = `"funnel copy"`; the board card's declared field `now` is the NOW banner (`board.py:337`). `tests/test_board.py:85` asserts it at tier M. | Satisfied as long as `now` is inside `want` at M — measured `deck_want("board",12,"M") == 5`, so all five fields. ✅ |
| P-12 | The proposal's drop-order tables are implemented faithfully in `deck.py`. | premise | ✅ TRUE | `PROPOSAL.md:264-269` table vs `deck.py:71-99` — weights, appetite, floor and ceiling match cell for cell. | `deck.py` is the spec. No re-derivation needed. |
| P-13 | The declared "230 must pass" is achievable alongside the rewrite. | hypothesis | ❓ **UNDECIDABLE until D1 is settled** | Under D1-A (one canvas) ~14 assertions in 6 files break by construction. Under D1-B they are preserved by construction. | **Blocks the gate.** Dispositioned by choosing D1. |

### Measured geometry (C-39 — every threshold this batch is keyed on, executed, not predicted)

`python -c "from desk import deck; ..."` over the six sizes `tests/test_smoke.py` drives:

| size | tier | grid (cols,rows,cw,ch) | shown | shed | rows per card | want per card |
|---|---|---|---|---|---|---|
| 30x8 | S | (1,2,28,2) | board, focus | **capture, record** | 2/2 | 2/2 |
| 40x12 | S | (1,3,38,2) | board, focus, record | **capture** | 2/2/2 | 2/2/2 |
| 58x14 | M | (2,2,27,5) | all 4 | — | b6 c5 f7 r4 | b3 f4 c4 r3 |
| 80x24 | M | (2,2,38,10) | all 4 | — | b12 c9 f14 r7 | 5/5/5/5 |
| 120x34 | L | (2,2,58,15) | all 4 | — | b13 c11 f15 r8 | 5/5/5/5 |
| 160x44 | L | (2,2,78,20) | all 4 | — | b13 c11 f15 r8 | 5/5/5/5 |

Two facts worth naming: **58x14 is already M** (so the M form must survive a 27-cell card),
and **160x44 allocates exactly what 120x34 does** — the ceilings bind, which is the
"a card with nothing more to say gets nothing" law holding. Both are AT fixtures.

---

## 2.8 — Decisions required before Phase 1 closes

**D1 · The widget architecture.** *(blocks P-13)*
- **A** — one full-screen canvas `Static`, faithful to the reference. Breaks ~14 assertions
  in 6 files. **Not recommended** (violates "all 230 must pass").
- **B — repurpose the four `#tile-*` Statics as the four CARDS**; `#strip` becomes the deck
  container; `#stage`/`#stage-body` stay exactly as they are and remain the MODE that `b`/`f`/
  `c`/`m`/`d` open. Every pinned id survives; `#strip`, `.tile` and `.active-tile` have **zero**
  test references and are free to redesign. Matches `deck.py:14-17` — *"THE STAGE IS NOT A
  SIZE."* **Recommended.**
- **C** — a new deck container alongside the existing strip. Two shells competing; rejected
  as unjustified asymmetry.

**D2 · Shedding.** A shed card is `display=False`, never removed from the tree (forced by P-8).

**D3 · The focus card's head carries the run mark.** Forced by P-10. The head's right side
shows the state mark + clock (`▸ 25:00`), which is a fact about the timer, not decoration.
The alternative — always appending the glance line at every tier — is rejected: it is not a
declared field, and it would violate "space is information-proportional".

**D4 · `focus.render_card` routes fire colour through `hearth_lines`.** Forced by P-9. The
hue-ration law is **not** edited.

**D5 · The geometry seat governs, not CSS.** Card widths/heights are set from
`deck.plan`/`deck_rows` in `_paint`; `desk.tcss` keeps only static chrome (ground, rules,
the `#stage.hidden` rule). Otherwise the seat would be advisory and the tests vacuous.

**D6 · `render_card` is ADDITIVE.** `render_tile` / `render_body` keep their current
signatures and defaults — 11 test files depend on them.

**D7 · The ribbon clock.** §5.1 drops it below 58 cells. `#clock` is queried by
`tests/test_smoke.py:41` at 40x12 and 30x8 → `display=False`, not removed. Same rule as D2.

---

## Evidence checklist (Phase 0)

- [x] Every candidate story carries a black-box AC at the behavior level — §2.6, AT-01..03.
- [x] Base ref recorded before derivation — `main` @ `4dc7ed2`, `PLAN.md` §Base currency.
- [x] Already-shipped check per story — backlog §Open "THE GATE" confirms all three are open.
- [x] Premise table executed against disk, not cited — §2.7, 13 rows, 5 FALSE / 1 UNDECIDABLE.
- [x] Every geometry threshold this batch keys on is **measured**, not predicted — §2.7 table.
- [x] Reverse-impact census run over the whole `tests/` tree (C-26) — recorded as R1–R5 in `PLAN.md`.
- [ ] Kickoff authorization — **NOT given**; asked at this gate.
