# Quick Spec — desk: the approved reimagining, ported into the real app

- **Status:** CLOSED 2026-07-30 (increments 1-3, 4a, 5, 6, 7 shipped; 4b/4c gated)
- **Branch:** `redesign-deck`
- **Base ref:** `main` @ 3fc3880
- **Flow revision:** fast-dev-flow as loaded 2026-07-30 (local; remote manifest
  `docs/FLOW-VERSION.md` not present in this repo — PULL check recorded as a gap)
- **Source of truth:** `_tui_synthesis/PROPOSAL.md` (approved in full),
  `_tui_synthesis/desk_final.py` (reference model, 74/74),
  `_tui_synthesis/verify_final.py` (the laws)

## 1. Objective

Port the approved reimagining out of the `_tui_synthesis` reference model and
into desk's real modules, in seven supervised increments. The reference model is
a **model**: its seats are re-implemented in desk's own modules, never imported
at runtime.

## 2. Scope note — this batch is SEVEN increments, not three

fast-dev-flow's escape hatch fires above three increments in phase B. It is
**declared here rather than tripped silently**: the operator approved the
roadmap as seven separate cycles, each ≤5 files with its own gate and commit,
which is seven small batches sharing one spec rather than one oversized batch.
If any single increment needs a second sitting or exceeds its file cap, that
increment promotes — not the whole batch.

## 3. Acceptance criteria (observable)

### Inc 1 — the journal line (the gate)
- **AC-1.1**: when `Pomodoro.tick()` returns True, one JSON object is appended
  to `~/.desk/pomodoros.jsonl` carrying `started_at`, `ended_at`, `seconds`,
  `outcome`.
- **AC-1.2**: when `Pomodoro.skip()` runs, one object with `outcome:"skipped"`
  is appended.
- **AC-1.3**: given a journal with N lines, after one more completion the file
  has N+1 lines and the first N are byte-identical (append-only, never rewrite).
- **AC-1.4**: given a missing `~/.desk/` directory, the first append creates it
  and the line lands.
- **AC-1.5**: given an unwritable journal path, `tick()` still returns True and
  raises nothing (the timer never dies because the log did).

### Inc 2 — the ember boundary
- **AC-2.1**: `fire_cells(0.9) > fire_cells(0.5) > fire_cells(0.1)` with a
  range ≥ 3x (today's shuffle reads 270/268/147 — a 1.8x range, and 90 % vs
  50 % differ by 2 cells).
- **AC-2.2**: the control test re-implements the shipped shuffle and asserts
  the law calls it flat.
- **AC-2.3**: every hearth row is exactly the same visible width (existing law,
  must stay green).

### Inc 3 — register
- **AC-3.1**: `grep -rn "your" desk/*.py` returns no hit inside a rendered UI
  string (the `capture.py` module docstring and the quoted capture prompts are
  the two declared exceptions).

### Inc 4 — the deck S/M/L
- **AC-4.1**: at 40x12 the deck renders 3 cards and names the shed one; at
  80x24 and 120x34 it renders 4.
- **AC-4.2**: the size thresholds sit at `card_h < 5` (S) and `card_h >= 12`
  (L) — the rename moved no threshold.
- **AC-4.3**: a field is dropped whole or kept whole; no card renders a header
  and nothing else.

### Inc 5 — the day-close (`d`)
- **AC-5.1**: `d` opens the close screen; `esc` leaves it.
- **AC-5.2**: given an EMPTY journal the close renders an honest empty state
  and no numeric figure.
- **AC-5.3**: given a journal with entries, every figure shown is derived from
  those entries.

### Inc 6 — the animations
- **AC-6.1**: each declared ambient has a period ≥ 2000 ms and each transition
  ≤ 400 ms — nothing in the illegal 400–2000 ms gap.
- **AC-6.2**: the ember's carved counter is byte-identical across all four
  breath phases.
- **AC-6.3**: the flame line's mean height does not move with `phase`.

### Inc 7 — cleanup
- **AC-7.1**: `_tui_synthesis/frames/{ledger,telar}_*.txt` are gone.
- **AC-7.2**: README claims match what the code does.

## 4. Out of scope

- Pushing. The operator pushes.
- Moving `_HIGH` instead of dropping `orange` (proposal §2.1 offered it; the
  approved decision is the glyph house `!2`).
- Changing `hints.py`'s capture-mode key list (see the premise table).

## 5. Premise table (C-43)

| Premise | Tier | Verdict | Executed evidence |
|---|---|---|---|
| `tick()` has a success branch returning True | premise | ✅ TRUE | `focus.py:246` — `return True` inside `if self.remaining == 0` |
| `app.py:142-146` already catches exceptions around the tick | premise | ❌ **FALSE** | `sed -n '136,151p' desk/app.py \| grep try` → no match. There is **no** try/except in `_tick`. **Consequence:** the journal append must swallow its own errors (AC-1.5), matching `Pomodoro.load`'s declared "never raises" convention at `focus.py:215`. |
| `~/.desk/pomodoros.jsonl` does not exist yet | premise | ✅ TRUE | `ls ~/.desk/pomodoros.jsonl` → No such file. `~/.desk/` holds config.json, record.json, state.json, transcripts/ |
| `focus.py:164-166` is the shuffle drain | premise | ✅ TRUE | read: `random.Random(seed).shuffle(order)` / `lit = set(order[:round(frac*len(order))])` |
| the shipped drain is flat at 90/50 | hypothesis | ✅ TRUE | proposal §3 table 270/268/147; **re-measured in Inc 2 against desk's own `hearth_lines`**, not taken on the proposal's word |
| `picker.py:268` says "your clipboard" | premise | ✅ TRUE | `grep -rn "your" desk/*.py` → picker.py:268, record.py:365, capture.py:6 (docstring) |
| desk.exe is not running | premise | ✅ TRUE | `tasklist \| grep desk.exe` → not running. `~/.desk/state.json` is uncontended. |
| baseline suite is green | premise | ✅ TRUE | `python -m pytest -q` → **160 passed** in 9.80 s |
| `hints.py:46-49` claims letter keys don't work in capture, but `app.py:55-59` marks b/f/c/m `priority=True` | premise | ❓ **UNDECIDABLE — declared OUT OF SCOPE in writing** | `tests/test_hints.py:48 test_capture_only_shows_keys_that_work` **encodes the current behaviour**. Per the operator's rule, surfaced not changed. Carried to the backlog. |
| the reference model is a model, not a dependency | hypothesis | to verify at close | no `_tui_synthesis` import may appear under `desk/` |

## 6. Security flags

Scanned objective + criteria + description. **`security_required: false`**, with
the near-misses named rather than passed over in silence:

- **`user input` / `file upload`** — no new input surface. The `d` screen is
  read-only over a file desk itself wrote.
- **`.env` / `credential` / `secret`** — none. The journal records durations and
  timestamps; **no note text, no project name typed by the user, no path.**
- **new write to user state** — the one genuinely new thing. It is
  **append-only**, to a **new** file, never touching `state.json`, and it fails
  silently by design (AC-1.5) so a disk problem cannot kill the timer.

The last item is not on fast-dev-flow's trigger list but is the riskiest line in
the batch, so it is treated as if it were: bounded, append-only, crash-safe, and
tested against a read-only path.
