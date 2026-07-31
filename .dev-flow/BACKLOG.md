# desk — backlog

The single cross-batch queue shared by `/dev-flow` and `/fast-dev-flow`. One
file: shipped items get marked here, open items carry forward, nothing is
dropped silently.

- **Base ref:** `main` @ 4ef3c91 (after the wiring batch; NOT pushed — Javier pushes)
- **Last refresh:** 2026-07-30 — batch `2026-07-30-batch-01` "wiring the deck" (dev-flow, on `main`)

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
| **THE GATE — the deck is wired; `deck.py` governs the live layout** | batch-01 | c239e5e |
| **Per-panel `render_card` S/M/L seats + `hearth_lines(rows=…)`** | batch-01 | 95a691d |
| **A shed card is named (key bar) + marked (ribbon)** — AC-4.1 now fully met | batch-01 | c239e5e |
| README describes the resizing deck, not the old strip | batch-01 | 4ef3c91 |

## Open

### From the wiring batch (`2026-07-30-batch-01`)
- ~~HIGH · `record.py` renders two unescaped external strings~~ **SHIPPED**
  (`desk/markup.py` + 14 sites, `tests/test_markup_safety.py`). The scan that
  preceded the fix found the class was **13 sinks, not 2**, and that
  `rich.markup.escape` — which the other four modules use — is **insufficient
  for Textual's parser**: it only escapes `[` before `a-z#/@`, so `[Bold]`,
  `[_x]` and `[$accent]` survive it and become live spans.
- **Four modules still escape with rich's `escape`** — `board.py`, `capture.py`,
  `close.py`. Their sinks are board task titles, project names, the capture
  prompt and the journal error, so the exposure is style injection and text
  corruption, not action dispatch (no `@` tag survives rich's escape). The fix is
  a one-line import swap per file to `from .markup import esc`; it was left out
  of the batch only to stay inside the 5-file cap.
- **`notify()` eats desk's own brackets.** Five sites say
  `pip install desk[record]` / `desk[web]` and render as `pip install desk` —
  the instruction loses the part that matters. Fixing it requires updating
  `tests/test_webui.py:231`, which asserts on the RAW markup string rather than
  what is rendered (the vacuous-oracle shape). Reverted from this batch for the
  cap; both belong together.
- **Three existing escape tests are vacuous oracles.** `tests/test_board.py:73`,
  `tests/test_capture.py:79` and `tests/test_card_seats.py:316` assert
  `"\[red]" in output` — a substring check on the markup string. It proves
  `esc()` ran and cannot fail while the output is still live under Textual.
  `tests/test_markup_safety.py` shows the replacement: parse the render and
  compare its span set against a benign control.
- **A hostile `board.json` title still breaks the row contract at the boundary.**
  Embedded newlines survive `normalize` (`board.py:119-123`) and `_emit` measures
  with `len()` not `cell_len`, so a CJK title overflows. Mitigated *defensively*
  in the cards (lines clamped, `overflow: hidden`); the boundary fix — strip
  control characters on load, measure in cells — is still open.
- **`board.py:382` is quadratic** — `t in doing` is list membership over dicts,
  43 ms at 2 000 tasks, on the 1 s repaint lane. One line: use an id set.
- **The board ledger is now permanently visible at L.** Client project names sit
  on screen for any screen share or demo recording. A design consequence of the
  approved proposal, not a defect — but worth a redaction key (~3 lines in
  `board.py:389`) before desk is shown on a client call.
- **Ad-hoc probe scripts bypass `tests/conftest.py`.** Its autouse fixture
  redirects every live-state path, but only under pytest. Driving `Deck()` from a
  throwaway `python -` script writes the operator's real `~/.desk/state.json`;
  it happened during this batch. Content came out byte-identical because the
  timer was idle — luck, not design. Worth a tiny `desk.testing.isolate()` helper
  so a probe cannot forget.
- **The carved clock is renounced below 30 cells.** At 86x24 the focus card is 26
  wide (`deck.CARD_MIN`) and the clock needs 30, so the ember burns bare and the
  dots row carries `▸ 12:34`. Correct per "renounce whole", but it means the
  three-column deck never shows the carved clock. Revisit if 3-col is common.
- **`record`'s idle meter holds two blank intake rows** so `auto`/`whisper` do
  not jump when recording starts. Constant geometry over dense idle — arguable.

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

### From the security review (2 LOW left open, deliberately)
- **The close re-reads and re-parses the whole journal once a second** while the
  panel is open (`close.py:read_journal`, no cache; `app.py:_paint` runs every
  tick). Not a problem at ~650 KB per decade, but the file has no rotation, no
  pruning and no size cap, and it is the one structure in the batch with no
  ceiling on it. Fix: cache on mtime, or have `Deck` hold the parsed rows and
  pass them to `render_body(rows=...)` — the parameter already exists.
- **A torn write silently consumes the NEXT good record.** `append_journal`
  writes the newline as a suffix, so a crash mid-write leaves a fragment that
  the following append concatenates onto. Costs one valid record in addition to
  the torn one; `read_journal` skips the result cleanly, so it is data loss and
  never a crash. Fix if wanted: write `"\n" + payload + "\n"` so a torn line
  self-terminates.
- **No way to clear or prune the journal from inside desk.** Called out as the
  operator's only escape hatch if the file is ever damaged by something other
  than desk, and as a privacy affordance: the journal is a permanent
  second-resolution record of when Javier works and how often he abandons an
  interval. Fine on a personal machine; worth knowing before desk is demoed on a
  shared or client-facing one.

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
