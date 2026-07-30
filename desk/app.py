"""The desk deck: one frameless window, a compact live strip that expands into
panels on demand.

This is the SHELL (increment 1). The three panels — Board, Focus, Capture —
are wired for minimize/expand and carry placeholder bodies; later increments
fill them in:
  - Focus   : braille pomodoro clock          (increment 2)
  - Board   : reads ~/.taskboard/board.json    (increment 3)
  - Capture : prompts -> Obsidian daily note    (increment 4)

The one non-obvious rule baked in here: a focusable Input sitting in the widget
tree silently swallows the single-key panel hotkeys (b/f/c). We keep the capture
Input `can_focus = False` except while the Capture panel is open, and make the
panel-switch bindings `priority` so they fire regardless of focus.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Input, Static

from . import board
from . import capture
from . import close
from . import deck
from . import focus
from . import hints
from . import record
from .picker import AudioPicker, UrlPrompt

PANELS = ("board", "focus", "capture", "record", "close")
BOARD_POLL_TICKS = 5          # auto-reload board.json every ~5s; F5 forces now

# palette (kept here until the shared `desk` core is extracted in a later pass)
ACCENT = "#2dd4bf"

# the deck's four cards, and how each one is named and reached
CARD_ID = {"board": "#tile-board", "focus": "#tile-focus",
           "capture": "#tile-capture", "record": "#tile-record"}
CARD_HEAD = {"board": "BOARD", "focus": "FOCUS",
             "capture": "CAPTURE", "record": "REC"}
CARD_KEY = {"board": "b", "focus": "f", "capture": "c", "record": "m"}
RIBBON_CLOCK_MIN_W = 58       # below this the ribbon drops the clock (PROPOSAL 5.1)
# The ribbon's own mark for a card the deck could not seat. The key bar names
# the shed card in words, but at 28 cells the words and the way out do not both
# fit and the way out wins — so the ribbon carries the mark that is always
# affordable. Four letters fit in any window desk runs in.
RIBBON_SHED = "·"


def seats(w: int, h: int, pinned=()) -> tuple:
    """(tier, {card: (x, y, w, h)}, shown, shed) for a `w` x `h` window.

    Pure: no widget is touched, so the whole layout can be swept over every size
    without booting an app. This is the ONE place the deck's geometry becomes
    positions — `desk.tcss` carries no card size at all, because a stylesheet
    that also had an opinion would make the seat advisory and every test of it
    vacuous.

    The floors are not defensive noise. `deck.plan` divides the window among the
    cards and its degenerate branch returns `w - 2` unclamped, so a 0x0 window —
    which is what `self.size` reports before the first layout — yields a card
    width of -2, and a negative width is a negative slice deep inside a
    renderer."""
    w = max(int(w), deck.CARD_MIN + 2)
    h = max(int(h), deck.CHROME + deck.CARD_MIN_H)
    tname = deck.tier(w, h)
    grid, shown, shed = deck.plan(w, h, pinned=pinned)
    cols, _rows, cw, _ch = grid
    cw = max(1, cw)
    body_h = max(1, h - deck.CHROME)
    rows = deck.deck_rows(shown, cols, body_h, tname)
    out: dict[str, tuple[int, int, int, int]] = {}
    for gc in range(cols):
        # the same partition `deck_rows` used, or a card would be sized for one
        # column and placed in another
        mine = [c for i, c in enumerate(shown) if i % cols == gc]
        if not mine:
            continue
        gaps = len(mine) - 1
        free = body_h - sum(rows[c] for c in mine)
        # SPACING YIELDS TO CONTENT, then air groups: a base gap only if every
        # gap can have one, then two thirds of what is left spread between the
        # cards (capped), and the remainder stays as bottom margin. Air between
        # two cards groups them; air at the bottom is just a remainder.
        base = deck.VGAP if free >= gaps * deck.VGAP else 0
        slack = max(0, free - gaps * base)
        per = min(4, slack * 2 // 3 // gaps) if gaps else 0
        y = 0
        for j, c in enumerate(mine):
            if j:
                y += base + per
            out[c] = (1 + gc * (cw + deck.GUTTER), y, cw, rows[c])
            y += rows[c]
    return tname, out, shown, shed


class Deck(App):
    """The always-on-top deck. `mode` is either "strip" (compact) or a panel."""

    CSS_PATH = "desk.tcss"
    # Textual's default AUTO_FOCUS="*" auto-focuses the first focusable widget on
    # mount — here the capture Input — which then swallows the global hotkeys
    # until an `esc` releases focus (the "ribbon shows but nothing works until I
    # mash keys + esc" bug, intermittent because it's a mount-timing race). The
    # deck drives everything from App bindings and only focuses the Input when
    # Capture opens, so nothing should be auto-focused.
    AUTO_FOCUS = None

    BINDINGS = [
        # priority: fire even when the capture Input is focused
        Binding("b", "expand('board')", "Board", priority=True),
        Binding("f", "expand('focus')", "Focus", priority=True),
        Binding("c", "expand('capture')", "Capture", priority=True),
        Binding("escape", "collapse", "Strip", priority=True),
        Binding("m", "expand('record')", "Record", priority=True),
        Binding("d", "expand('close')", "Close the day", priority=True),
        ("o", "open_board", "Open board"),
        ("t", "open_transcripts", "Transcripts"),
        Binding("i", "transcribe_file", "Transcribe file", show=False),
        Binding("u", "transcribe_url", "Transcribe URL", show=False),
        Binding("x", "cancel_job", "Cancel download", show=False),
        ("f5", "refresh", "Refresh"),
        ("q", "quit", "Quit"),
        # pomodoro controls — shown inside the Focus panel, hidden from the footer
        Binding("space", "primary", "Start/Pause", show=False),
        Binding("s", "pomo_skip", "Skip", show=False),
        Binding("r", "pomo_reset", "Reset", show=False),
        Binding("plus", "pomo_add", "More pomo", show=False),
        Binding("equals_sign", "pomo_add", "More pomo", show=False),
        Binding("minus", "pomo_remove", "Fewer pomo", show=False),
        Binding("a", "auto_toggle", "Auto-stop", show=False),
    ]

    mode = reactive("strip")
    clock = reactive("--:--:--")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """While a modal (the audio picker) is open, disable the deck's own
        hotkeys EXCEPT `collapse` — escape is repurposed (in action_collapse) to
        close the modal, and everything else must stay inert behind it."""
        if len(self.screen_stack) > 1:
            return action == "collapse"
        return True

    def compose(self) -> ComposeResult:
        # the chrome is exactly `deck.CHROME` rows: this ribbon and the key bar
        with Horizontal(id="ribbon"):
            yield Static(id="ribbon-cards")
            yield Static(id="clock")
        # the deck. Its cards are placed absolutely from `seats`, so the order
        # they are yielded in carries no layout meaning.
        with Container(id="strip"):
            yield Static(id="tile-board", classes="tile")
            yield Static(id="tile-focus", classes="tile")
            yield Static(id="tile-capture", classes="tile")
            yield Static(id="tile-record", classes="tile")
        with Vertical(id="stage", classes="hidden"):
            yield Static(id="stage-body")
            yield Input(placeholder="type a thought, hit enter…", id="cap-input")
        # our own legend, not Footer: Footer silently drops keys that don't fit
        # (quit vanished at 80 cols) and never changed with the open panel.
        yield Static(id="hints")

    def on_mount(self) -> None:
        self.pomo = focus.Pomodoro.load()
        self.board_data = board.load()
        self._prompt_i = 0
        self._last_saved = None
        self._ticks = 0
        self._beat = False               # toggles each tick for the living panels
        self._fast = 0                   # 10 Hz counter: VU repaints + spinner phase
        self._fetch_info: dict = {}      # live state of a web-video download
        self._cancel_fetch = False       # set by `x`, read by the fetch worker
        self._rec = record.Recorder()
        self._rec_state = "idle"
        self._last_transcript = None
        _rs = record.load_settings()
        self._auto_on = _rs["enabled"]
        self._auto_min = _rs["minutes"]
        inp = self.query_one("#cap-input", Input)
        inp.display = False
        inp.can_focus = False          # else it steals the b/f/c hotkeys at rest
        self.set_focus(None)           # belt-and-suspenders vs any mount auto-focus
        self._paint()
        self.set_interval(1.0, self._tick)
        # a fast lane just for the live VU meter — the 1 s tick is far too slow
        # for a level meter to look alive. No-op unless actually recording.
        self.set_interval(0.1, self._meter_tick)

    def _meter_tick(self) -> None:
        """The 10 Hz lane: repaints the record body while the VU meter is live OR
        a download is running, so both track reality instead of crawling at 1 fps.
        A no-op in every other state."""
        self._fast += 1
        if self.mode == "record" and self._rec_state in ("recording", "fetching"):
            self.query_one("#stage-body", Static).update(self._body("record"))

    def _tick(self) -> None:
        self.clock = datetime.now().strftime("%H:%M:%S")
        self._ticks += 1
        self._beat = not self._beat          # 1 fps parity for the living panels
        if self._ticks % BOARD_POLL_TICKS == 0:
            self.board_data = board.load()      # gentle auto-poll; F5 forces now
        completed = self.pomo.tick()
        if completed:
            self.bell()
        if self.pomo.running or completed:
            self.pomo.save()          # keep remaining fresh across restarts
        if self._rec_state == "recording" and record.should_autostop(
                self._rec.seconds, self._auto_on, self._auto_min):
            self._rec_toggle()          # auto-finish: stop + transcribe
        self._paint()

    # ---- expand / collapse ------------------------------------------------
    def action_expand(self, which: str) -> None:
        if which not in PANELS:
            return
        self.mode = which
        self.query_one("#stage").remove_class("hidden")
        inp = self.query_one("#cap-input", Input)
        if which == "capture":
            inp.display = True
            inp.can_focus = True
            inp.focus()
            inp.placeholder = capture.pick_prompt(self._prompt_i)
        else:
            self._hide_input()
        self._paint()

    def _hide_input(self) -> None:
        """Fully disengage the capture text box so it can't swallow global keys.
        Setting display/can_focus alone can leave focus stuck on the hidden Input
        (Textual keeps the stale reference); that intermittently ate b/f/c/m/q
        after visiting Capture and made the deck feel dead. Release focus too."""
        inp = self.query_one("#cap-input", Input)
        inp.display = False
        inp.can_focus = False
        if self.focused is inp:
            self.set_focus(None)

    def action_collapse(self) -> None:
        if len(self.screen_stack) > 1:          # a modal is open -> escape closes IT
            self.screen.dismiss(None)
            return
        self.mode = "strip"
        self._hide_input()
        self.query_one("#stage").add_class("hidden")
        self._paint()

    def action_refresh(self) -> None:
        """Reload the board from disk immediately (don't wait for the poll)."""
        self.board_data = board.load()
        self._paint()
        self.notify("refreshed")

    def action_open_board(self) -> None:
        """Launch the full taskboard app in a separate terminal window — WezTerm
        if available, otherwise a new default console."""
        import shutil
        import subprocess
        import sys
        try:
            if shutil.which("wezterm"):
                subprocess.Popen(["wezterm", "start", "--", "taskboard"])
            elif sys.platform == "win32":
                subprocess.Popen(["taskboard"], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(["taskboard"])
            self.notify("opening taskboard…")
        except Exception as exc:
            self.notify(f"couldn't open taskboard: {exc}", severity="error")

    def action_open_transcripts(self) -> None:
        """Open the transcripts folder (~/.desk/transcripts) in the OS file
        manager. Created if it doesn't exist yet, so the key always works."""
        import os
        import subprocess
        import sys
        d = record.TRANSCRIPTS_DIR
        try:
            d.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(d))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(d)])
            else:
                subprocess.Popen(["xdg-open", str(d)])
            self.notify(f"opening {d}")
        except Exception as exc:
            self.notify(f"couldn't open transcripts: {exc}", severity="error")

    def action_pomo_toggle(self) -> None:
        self.pomo.toggle(); self.pomo.save(); self._paint()

    def action_pomo_skip(self) -> None:
        self.pomo.skip(); self.pomo.save(); self._paint()

    def action_pomo_reset(self) -> None:
        self.pomo.reset(); self.pomo.save(); self._paint()

    def action_pomo_add(self) -> None:
        if self.mode == "record":
            self._auto_min = record.clamp_minutes(self._auto_min + record.AUTO_STEP)
            record.save_settings(self._auto_on, self._auto_min); self._paint(); return
        self.pomo.add(); self.pomo.save(); self._paint()

    def action_pomo_remove(self) -> None:
        if self.mode == "record":
            self._auto_min = record.clamp_minutes(self._auto_min - record.AUTO_STEP)
            record.save_settings(self._auto_on, self._auto_min); self._paint(); return
        self.pomo.remove(); self.pomo.save(); self._paint()

    def action_auto_toggle(self) -> None:
        if self.mode != "record":
            return
        self._auto_on = not self._auto_on
        record.save_settings(self._auto_on, self._auto_min)
        self._paint()

    def action_primary(self) -> None:
        """space: the main action of the current panel (record toggle in Record,
        pomodoro start/pause elsewhere)."""
        if self.mode == "record":
            self._rec_toggle()
        else:
            self.action_pomo_toggle()

    def _rec_toggle(self) -> None:
        if not record.AVAILABLE:
            self.notify("recording needs: pip install desk[record]", severity="warning")
            return
        if self._rec.running:
            wav = self._rec.stop()
            self._rec_state = "transcribing"
            self._paint()
            self.run_worker(lambda: self._run_transcription(wav), thread=True,
                            exclusive=True, group="transcribe")
        else:
            try:
                self._rec.start()
                self._rec_state = "recording"
            except Exception as exc:
                self._rec_state = "idle"
                self.notify(f"can't record: {exc}", severity="error")
            self._paint()

    def _run_transcription(self, wav) -> None:
        """Runs in a worker thread — never blocks the UI."""
        try:
            if not wav:
                raise RuntimeError("no audio captured")
            from . import transcribe
            text = transcribe.transcribe(wav)
            transcribe.save_transcript(wav, text)
            self.call_from_thread(self._on_transcribed, text, None)
        except Exception as exc:
            self.call_from_thread(self._on_transcribed, None, str(exc))

    def _on_transcribed(self, text, err) -> None:
        self._rec_state = "idle"
        self._fetch_info = {}
        if err:
            self._last_transcript = f"(error: {err})"
            self.notify(f"transcription failed: {err}", severity="error")
        else:
            self._last_transcript = text or "(no speech detected)"
            self.notify("transcript saved")
        self._paint()

    # ---- transcribe an EXISTING file (in-app, via the picker) --------------
    def action_transcribe_file(self) -> None:
        """Open the audio picker to transcribe a file already on disk. Separate
        from — and never disturbs — the live recording flow."""
        from . import transcribe
        if not transcribe.AVAILABLE:
            self.notify("transcription needs: pip install desk[record]", severity="warning")
            return
        if self._rec_state != "idle":
            self.notify("busy — finish the current job first", severity="warning")
            return
        self.push_screen(AudioPicker(start=Path.home()), self._on_file_picked)

    def _on_file_picked(self, picked) -> None:
        """The picker hands back a Path (local file) or a str (a web URL)."""
        if not picked:
            return
        if isinstance(picked, str):
            self._start_url_job(picked)
            return
        self._enter_record_panel("transcribing")
        self.run_worker(lambda: self._run_file_transcription(picked), thread=True,
                        exclusive=True, group="transcribe")

    def _enter_record_panel(self, state: str) -> None:
        self._rec_state = state
        self.mode = "record"
        self.query_one("#stage").remove_class("hidden")
        self._hide_input()
        self._paint()

    # ---- transcribe a WEB VIDEO (fetch its audio, then transcribe) ---------
    def action_transcribe_url(self) -> None:
        from . import fetch
        from . import transcribe
        if not transcribe.AVAILABLE:
            self.notify("transcription needs: pip install desk[record]", severity="warning")
            return
        if not fetch.AVAILABLE:
            self.notify("web video needs: pip install desk[web]", severity="warning")
            return
        if self._rec_state != "idle":
            self.notify("busy — finish the current job first", severity="warning")
            return
        self.push_screen(UrlPrompt(), self._on_url_entered)

    def _on_url_entered(self, url: str | None) -> None:
        if url:
            self._start_url_job(url)

    def action_cancel_job(self) -> None:
        """`x`: actually stop a running download. Only the FETCH is interruptible
        — once whisper has the audio there is no safe mid-run abort — so say so
        instead of pretending the key did something."""
        if self._rec_state == "fetching":
            self._cancel_fetch = True
            self._fetch_info["status"] = "cancelling…"
            self._paint()
            self.notify("cancelling the download…")
        elif self._rec_state == "transcribing":
            self.notify("transcription can't be cancelled — it's nearly done",
                        severity="warning")

    def _start_url_job(self, url: str) -> None:
        self._cancel_fetch = False
        self._fetch_info = {"url": url, "site": None, "title": None,
                            "duration": None, "frac": None, "status": "reading…"}
        self._enter_record_panel("fetching")
        self.run_worker(lambda: self._run_url_job(url), thread=True,
                        exclusive=True, group="transcribe")

    def _run_url_job(self, url: str) -> None:
        """Worker thread: pull the audio, then transcribe it. Progress is written
        into `_fetch_info`, which the 10 Hz lane paints — no widget is touched
        from this thread."""
        from . import fetch                 # bound before the try: the except
        from . import transcribe            # clause below names fetch.FetchCancelled
        try:
            def progress(frac, status):
                self._fetch_info.update(frac=frac, status=status)

            path, meta = fetch.fetch_audio(url, progress=progress,
                                           cancelled=lambda: self._cancel_fetch)
            self._fetch_info.update(title=meta.get("title"),
                                    duration=meta.get("duration"),
                                    site=meta.get("extractor"))
            self.call_from_thread(self._enter_record_panel, "transcribing")
            text = transcribe.transcribe_file(path)
            body = text if text.strip() else "_(no speech detected)_"
            dev = transcribe.active_device() or transcribe.planned_device()
            transcribe._write_md(
                path.with_suffix(".md"), meta.get("title") or path.name, body,
                transcribe.DEFAULT_MODEL,
                "GPU (float16)" if dev == "cuda" else "CPU (int8)",
                source=meta.get("webpage_url") or url)
            self.call_from_thread(self._on_transcribed, text, None)
        except fetch.FetchCancelled:
            self.call_from_thread(self._on_cancelled)       # a clean stop, not a failure
        except Exception as exc:
            self.call_from_thread(self._on_transcribed, None, str(exc))

    def _run_file_transcription(self, path: Path) -> None:
        """Worker thread: transcribe any audio file and write <name>.md beside it."""
        try:
            from . import transcribe
            text = transcribe.transcribe_file(path)
            body = text if text.strip() else "_(no speech detected)_"
            path.with_suffix(".md").write_text(
                f"# Transcript — {path.name}\n\n"
                f"- Generated: {datetime.now():%Y-%m-%d %H:%M}\n\n{body}\n",
                encoding="utf-8")
            self.call_from_thread(self._on_transcribed, text, None)
        except Exception as exc:
            self.call_from_thread(self._on_transcribed, None, str(exc))

    def _on_cancelled(self) -> None:
        """A cancelled download is a clean outcome, not an error: back to idle,
        no '(error: …)' pinned to the panel, and the partial file is gone."""
        self._rec_state = "idle"
        self._fetch_info = {}
        self._cancel_fetch = False
        self.notify("download cancelled")
        self._paint()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            try:
                note = capture.append_capture(text)
                self._last_saved = note.name
                self.notify(f"saved to {note.name}")
            except Exception as exc:                      # vault missing, etc.
                self._last_saved = None
                self.notify(f"couldn't save: {exc}", severity="error")
        event.input.value = ""
        self._prompt_i += 1
        event.input.placeholder = capture.pick_prompt(self._prompt_i)
        self._paint()

    # ---- rendering (placeholder content until later increments) -----------
    def _tiles(self) -> dict[str, str]:
        """The minimized live tiles. Real data arrives with each panel's
        increment; for now they are honest placeholders."""
        return {
            "board": board.render_tile(self.board_data, beat=self._beat),
            "focus": focus.render_tile(self.pomo, beat=self._beat),
            "capture": capture.render_tile(capture.pick_prompt(self._prompt_i)),
            "record": record.render_tile(self._rec_state, self._rec.seconds, self._rec.level),
        }

    def _body(self, which: str) -> str:
        if which == "close":
            return close.render_body()
        if which == "focus":
            # the ambient's phase comes from the 1 s tick: 4 phases = a 4000 ms
            # loop, which is the regime an ambient has to be in.
            return focus.render_body(self.pomo, beat=self._beat,
                                     phase=self._ticks)
        if which == "board":
            return board.render_body(self.board_data, beat=self._beat)
        if which == "record":
            return record.render_body(self._rec_state, self._rec.seconds,
                                      self._rec.level, self._last_transcript,
                                      self._auto_on, self._auto_min,
                                      fetch=self._fetch_info, phase=self._fast)
        return capture.render_body(capture.pick_prompt(self._prompt_i), self._last_saved)

    def _pinned(self) -> frozenset:
        """A card that is DOING something is the last thing the deck lets go.
        Shedding a running timer to keep an idle capture box on screen has the
        priorities backwards."""
        live = set()
        if self.pomo.running:
            live.add("focus")
        if self._rec_state != "idle":
            live.add("record")
        return frozenset(live)

    def _card_head(self, card: str, w: int) -> str:
        """The card's own name and the key that opens it, then a rule to the
        edge. This is the only chrome the four cards share — everything below it
        is each card's own idiom."""
        head, key = CARD_HEAD[card], CARD_KEY[card]
        n = max(0, w - len(head) - len(key) - 3)
        return f"[bold {ACCENT}]{head}[/] [dim]{key}[/dim] [#263041]{'─' * n}[/]"

    def _card_text(self, card: str, cw: int, ch: int, tiles: dict) -> str:
        """The card's body at its seat. Increment 1 gives every tier the glance
        form — the head plus the one line `render_tile` already returns — so the
        geometry can be wired and proven before the per-card S/M/L seats land."""
        lines = [self._card_head(card, cw)]
        if ch >= deck.GLANCE_ROWS:
            lines.append(tiles[card])
        return "\n".join(lines[:max(1, ch)])

    def _paint_deck(self, size=None) -> None:
        """Place and fill the four cards from the geometry seat."""
        size = size or self.size
        w = size.width or 80             # size is (0,0) before the first layout
        h = size.height or 24
        _tname, seat, _shown, shed = seats(w, h, pinned=self._pinned())
        self._shed = tuple(shed)
        tiles = self._tiles()
        for card, wid in CARD_ID.items():
            widget = self.query_one(wid, Static)
            # a shed card keeps its content and its place in the tree; only its
            # display goes. Nothing the operator could act on is destroyed just
            # because the window got small.
            x, y, cw, ch = seat.get(
                card, (1, 0, max(1, w - 2), deck.GLANCE_ROWS))
            widget.styles.offset = (x, y)
            widget.styles.width = cw
            widget.styles.height = ch
            widget.update(self._card_text(card, cw, ch, tiles))
            widget.display = card in seat
            (widget.add_class if self.mode == card
             else widget.remove_class)("active-tile")
        # the stage is a MODE, not a size: when it opens it takes the window,
        # so the deck stands down rather than sharing rows with it.
        self.query_one("#strip").display = self.mode == "strip"
        self._paint_ribbon(w, shed)

    def _paint_ribbon(self, w: int, shed) -> None:
        marks = []
        for card in deck.DECK_ORDER:
            key = CARD_KEY[card].upper()
            if card in shed:
                marks.append(f"[#3d4757]{key}{RIBBON_SHED}[/]")
            elif self.mode == card:
                marks.append(f"[{ACCENT}]{key} [/]")
            else:
                marks.append(f"[#6b7787]{key} [/]")
        self.query_one("#ribbon-cards", Static).update(" " + "".join(marks))
        clock = self.query_one("#clock", Static)
        clock.display = w >= RIBBON_CLOCK_MIN_W
        clock.update(f"[dim]{self.clock}[/dim]")

    def _paint(self, size=None) -> None:
        self._paint_deck(size)
        if self.mode in PANELS:
            self.query_one("#stage-body", Static).update(self._body(self.mode))
        self._paint_hints(size)

    def _paint_hints(self, size=None) -> None:
        """Re-render the key legend for the current mode at the current width.
        Called on every paint and on resize, so it always fits and always
        reflects the open panel — and now also names whatever the deck shed."""
        size = size or self.size
        width = size.width or 80               # size is (0,0) before first layout
        self.query_one("#hints", Static).update(
            hints.render(self.mode, width - 2, shed=getattr(self, "_shed", ())))

    def on_resize(self, event) -> None:
        # A Resize arrives BEFORE on_mount, so the panel state a full repaint
        # reads does not exist yet. The old handler only re-fitted the hint bar
        # and never noticed; repainting the deck here does, and it would crash
        # the app on launch rather than in a test.
        if not hasattr(self, "pomo"):
            return
        # `self.size` still reports the PREVIOUS size inside this handler —
        # measured, not assumed. Painting from it seats every card for the
        # window the app just left, which is a whole resize of lag. The old
        # handler had the same bug in the hint bar and nothing could see it.
        self._paint(event.size)


def main() -> None:
    Deck().run()


if __name__ == "__main__":
    main()
