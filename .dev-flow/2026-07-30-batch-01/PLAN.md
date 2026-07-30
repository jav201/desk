# PLAN — 2026-07-30-batch-01 · wiring the deck

**Living compendium.** Updated at every gate and checkpoint.

## Where we are

Phase 0 (story intake) complete, **awaiting the gate**. Nothing implemented. No file
in `desk/` or `tests/` modified.

## Objective

`desk/deck.py` — the S/M/L geometry seat — is built, tested (`tests/test_deck_geometry.py`,
10 laws) and **imported by nothing but its own test**. Wire it into the live app so the
deck actually resizes.

## Base currency (RC-1)

- Repo is **not a git remote clone with a live origin** for this work: operator directive is
  *work directly on `main`, commit per increment, NEVER push*. No `git fetch` / rebase step applies.
- `main` @ **`4dc7ed2`** — "Backlog: carry the two LOW findings and the journal-prune gap".
  Verified by `git log --oneline -1`.
- Flow revision: `~/.claude` @ **`061bf93`** ("flows: encode C-45 + publish a versioned manifest"),
  working tree clean. Flow is current — C-45 PULL discharged.
- Baseline suite: **230 passed in 20.31s** (`python -m pytest -q`, exit 0).
- `~/.desk/` live state baselined: 13 files, md5 + mtime recorded at
  `/tmp/desk-wiring/desk-state-baseline.{md5,mtime}`. Re-verified at batch close.

## Kickoff authorization — NOT YET GIVEN

Pending at this gate:
1. **Autonomy.** Does this batch run end-to-end autonomously (self-approving the
   Phase 1→4 gates), or does the operator approve each gate? Merge authority is moot —
   there is no PR; work lands as commits on `main` and the operator pushes.
2. **Decision-recording acknowledgement.** Every decision taken instead of asking gets
   logged here + in `state.json.decisions_log` + the post-mortem.

## Stories (Phase 0)

| id | story | INVEST verdict |
|---|---|---|
| US-01 | The deck lays out its cards for the window it is actually in, so a resize changes what is shown rather than only how it is clipped. | **READY** |
| US-02 | Each card renders its S / M / L form — a prefix of its declared fields, a field renounced whole and never truncated. | **READY** |
| US-03 | A shed card is named where the operator can see it, so nothing actionable leaves the screen silently. | **READY** (closes the half-met AC-4.1 in the backlog) |

Out of scope, explicitly: the `hints.py:46-49` vs `app.py:55-60` contradiction (operator
decision 3 — stays as-is); dropping `orange` (operator decision 2 — it stays); the journal
cache / prune / torn-write LOWs; the stage (`enter`) becoming a size.

## Roadmap · increment plan

Follows the split the backlog itself specified.

| inc | scope | files | AT |
|---|---|---|---|
| **1 (4b)** | The shell lays out four cards from `deck.plan` / `deck_rows` / `deck_want`; each card body is still the existing renderer, seated. Shed card NAMED. | `desk/app.py`, `desk/desk.tcss`, `desk/hints.py`, `tests/test_deck_wiring.py` (new) | AT-01, AT-03 |
| **2 (4c)** | Per-module `render_card` seats honouring `want` and the floors. | `desk/board.py`, `desk/focus.py`, `desk/capture.py`, `desk/record.py`, `tests/test_card_seats.py` (new) | AT-02 |

Expected total: **9 files** (operator lifted the 5-file cap for this task).

## Key decisions — OPEN, blocking the gate

See `01-requirements.md` §2.7 premise table and §2.8. D1–D7 need a call.

## Risks / watch-items

- **R1** The reference implementation `_tui_synthesis/desk_final.py` paints ONE `Static`.
  The live app's tests pin six widget ids. A literal port breaks ~14 assertions in 6 files.
- **R2** `tests/test_hue_ration.py:73` pins `RAMP_SEATS = {"hearth_lines","render_tile"}` by
  **call-frame provenance**. A `focus.render_card` that calls `temp_hex` directly fails it.
- **R3** `tests/test_motion.py:42` pins the literal `set_interval(1.0, self._tick)` inside
  `Deck.on_mount` by `inspect.getsource`. Reformatting that line breaks it.
- **R4** `tests/test_register.py` AST-scans every `desk/*.py` for second person; every new
  string literal is in scope.
- **R5** `tests/test_deck_geometry.py:134` text-scans every `desk/*.py` for the substring
  `_tui_synthesis`. New comments must not name the reference by that path.
- **R6** The refuted claim: opposite-sign column pairing does NOT make the breath mean
  invariant (measured 0.38 vs 0.17 dot-rows drift). Mainline dropped it. **Do not reintroduce.**

## Conventions honored

Card sovereignty (each panel keeps its own idiom; only container chrome is shared) ·
space is information-proportional · a field is renounced whole, never truncated ·
the app never addresses the reader in second person · severity keeps ONE hue.

## Test ledger

| point | base | −D | +A | post |
|---|---|---|---|---|
| batch start | 230 | 0 | 0 | **230** |

## Decision log

| # | date | decision | taken by |
|---|---|---|---|
| 1 | 2026-07-30 | Scaffolded `state.json` by hand rather than running `/dev-flow-init`; `.dev-flow/` already existed holding `BACKLOG.md`. | agent |
| 2 | 2026-07-30 | Routing confirmed as `/dev-flow` (not `/fast-dev-flow`): the backlog's own gate entry says "probably its own /dev-flow batch", and the change alters what the operator sees on every launch. | agent |
