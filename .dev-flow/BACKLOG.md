# desk — backlog

The single cross-batch queue shared by `/dev-flow` and `/fast-dev-flow`. One
file: shipped items get marked here, open items carry forward, nothing is
dropped silently.

- **Base ref:** `main` @ 3fc3880 (before this batch)
- **Last refresh:** 2026-07-30 — batch "the approved reimagining" (branch `redesign-deck`, NOT pushed)

## Shipped

| Item | Batch / PR | Ref |
|---|---|---|
| Focus ember-hearth + deck-wide pulse | living viz | #7 · d175f73 |
| Gantt flow current (taskboard) | living viz | jav201/taskboard#6 |
| GPU auto-detect + CPU fallback + device indicator | whisper GPU | #8 · 63354ab |
| Live VU meter (mic level, 10 fps, dB scale) | VU | #9 · 8bfa30e |
| `desk-transcribe` CLI for existing audio files | CLI | #10 · 38a5cc7 |
| In-app file transcription (`i` picker) | picker | #11 · 21fd4a9 |
| Web video → audio → transcript (`u`, `i`, CLI, `[web]` extra) | THIS batch | 11f9041, 6593eba |
| Braille-intake fetch treatment + clipboard prefill on `u` | THIS batch | (operator picked C + idea 9 after seeing the prototype) |
| Real download cancellation (`x`), partial cleaned up | web video | closes the honest gap flagged at first close |
| Pomodoro journal (`~/.desk/pomodoros.jsonl`, append-only) | reimagining | 0d843ad |
| Ember drains on a moving front (270/268/147 → 260/148/36) | reimagining | f9c6fc8 |
| Register: no second person in the app's own voice | reimagining | 0ecd07e |
| Hue ration: high priority to the glyph house, `_HIGH` deleted | reimagining | 4e77685 |
| Deck S/M/L geometry seat (`desk/deck.py`, logic only) | reimagining | f1f0661 |
| The day-close (`d`), reading the real journal | reimagining | 3aeb38b |
| Ember ambient in the glyph channel, 4000 ms, level basic | reimagining | b4776fb |
| Stale rev1 frames deleted; README matches the code | reimagining | THIS commit |

## Open

### THE GATE — the deck shell is built but not wired (reimagining batch)
- **`desk/deck.py` is not imported by anything yet.** The geometry, the S/M/L
  ladder and the drop-order tables are shipped and tested; the app still runs
  the original strip + single-stage shell. Wiring it means replacing `compose`,
  `_paint` and `desk.tcss` and giving every panel a `render_card(w, h, want)`
  seat — 8+ files against a 5-file cap, and it changes what the operator sees on
  every launch. **It needs an explicit go, and probably its own /dev-flow
  batch.** Split as planned: (4b) the shell renders four cards from `deck.plan`,
  each body still the existing renderer; (4c) the per-module card seats honouring
  `want` and the floors.
- **The shed card must be NAMED in the key bar.** At 40x12 the deck sheds
  `capture`; `plan` returns it, nothing prints it yet. AC-4.1 is half-met — the
  shedding is right, the announcement is missing. Belongs with 4b.

### Decisions waiting on the operator
- **Is `orange` dropped from the project palette?** Proposal §2.1 said yes. I did
  NOT do it: the collision it solved was orange-vs-`_HIGH`, and deleting `_HIGH`
  (4e77685) dissolves it. Measured, `orange` now sits 90 rgb units from the one
  reserved hue — further than `rose` (64) or `pink` (102), which nobody proposed
  dropping. Reversible either way; say the word.
- **`hints.py:46-49` vs `app.py:55-60`.** The hint bar tells capture mode that
  letter keys only get typed into the note, but `b`/`f`/`c`/`m`/`d` are all
  `priority=True`, which means they DO fire there. One of the two is wrong.
  `tests/test_hints.py:48` encodes the current behaviour, so it was surfaced and
  not silently changed. Decide which is the truth, then fix the other.

### Deferred by design (came out of this batch)
- **The fire's hot end is 45 rgb units from the overdue red** (`#ff4b34` at 86 %
  spent vs `#f43f5e`). They never share a panel and the ramp's seats are now
  checked by provenance, but it is the closest the one reserved hue comes to
  being crossed. Measured, not in the proposal.
- **The journal has no `project_id`.** The proposal's schema names one; desk's
  pomodoro is not bound to a project, so the field would be `null` on every
  line. Omitted rather than faked. Binding the timer to a project is a real
  feature, and it is what would let the close show per-project bars.
- **A real-terminal run is still unverified.** The app is now driven headless
  across 6 window sizes x 18 bindings (`tests/test_smoke.py`, 108 presses, zero
  errors), which covers `set_interval`, `on_resize` and every binding. What that
  cannot see is glyph coverage and colour in a real WezTerm.

### Deferred by design (came out of this batch)
- **Fetch treatments A and B are unbuilt.** The operator picked C (braille
  intake) after seeing the prototype; A (meter lane, reusing the VU geometry)
  was implemented first and then replaced. Both remain in the artifact
  `c60a8c5a-5139-481e-a463-3f12128842e9` if the call is ever revisited.
- **Time projection on the fetch bar** — steal treatment B's "~23:22 pulled"
  as a dim suffix on the status line, ONCE it's confirmed that near-CBR m4a is
  the common case (the mapping bytes→time is wrong under VBR, so shipping it
  now would be a confident lie).

### Carried from earlier batches
- **Pomodoro critical lub-dub** — 4 fps heartbeat under 2:00 remaining, via a
  `set_interval(0.25)` that only lives while `remaining < 120 and running`.
- **Board header wording** — desk's board shows generic `TODO/DOING/DONE`
  while the real phases are `Backlog/Doing/Done`. One-line change; awaiting a
  call from the operator.
- **`desk-transcribe` console script** — the entry point needs one
  `pip install -e .` to materialise, and that install FAILS while `desk` is
  running (WinError 32 on `desk.exe`) and can half-uninstall the package.
  Currently worked around with a `desk.pth`. Do a clean reinstall with desk
  closed.
- **taskboard: save-side validation follow-ups** — dead code `_URG_BRAILLE` /
  `AGENDA_GROUPS` in `views.py`; the agenda axis span is fixed; project-status
  editing is still unwired.
