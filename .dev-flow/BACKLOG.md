# desk — backlog

The single cross-batch queue shared by `/dev-flow` and `/fast-dev-flow`. One
file: shipped items get marked here, open items carry forward, nothing is
dropped silently.

- **Base ref:** `main` @ 21fd4a9 (before this batch)
- **Last refresh:** 2026-07-25 — batch "web video audio → transcript"

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

## Open

### Deferred by design (came out of this batch)
- **Fetch treatments A and B are unbuilt.** The operator picked C (braille
  intake) after seeing the prototype; A (meter lane, reusing the VU geometry)
  was implemented first and then replaced. Both remain in the artifact
  `c60a8c5a-5139-481e-a463-3f12128842e9` if the call is ever revisited.
- **Time projection on the fetch bar** — steal treatment B's "~23:22 pulled"
  as a dim suffix on the status line, ONCE it's confirmed that near-CBR m4a is
  the common case (the mapping bytes→time is wrong under VBR, so shipping it
  now would be a confident lie).
- **Cancel a running fetch** — esc collapses the panel but does NOT interrupt
  the worker. Caught during this batch's close: the hint used to read "esc
  cancels", which was a lie, and now reads "esc hides this · the job keeps
  running". Real cancellation (abort from the progress hook) is still unbuilt.

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
