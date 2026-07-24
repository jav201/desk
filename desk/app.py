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

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Input, Static

from . import board
from . import capture
from . import focus
from . import hints
from . import record

PANELS = ("board", "focus", "capture", "record")
BOARD_POLL_TICKS = 5          # auto-reload board.json every ~5s; F5 forces now

# palette (kept here until the shared `desk` core is extracted in a later pass)
ACCENT = "#2dd4bf"


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
        ("o", "open_board", "Open board"),
        ("t", "open_transcripts", "Transcripts"),
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

    def compose(self) -> ComposeResult:
        with Horizontal(id="strip"):
            yield Static(id="tile-board", classes="tile")
            yield Static(id="tile-focus", classes="tile")
            yield Static(id="tile-capture", classes="tile")
            yield Static(id="tile-record", classes="tile")
            yield Static(id="clock")
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

    def _tick(self) -> None:
        self.clock = datetime.now().strftime("%H:%M:%S")
        self._ticks += 1
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
        if err:
            self._last_transcript = f"(error: {err})"
            self.notify(f"transcription failed: {err}", severity="error")
        else:
            self._last_transcript = text or "(no speech detected)"
            self.notify("transcript saved")
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
            "board": board.render_tile(self.board_data),
            "focus": focus.render_tile(self.pomo),
            "capture": capture.render_tile(capture.pick_prompt(self._prompt_i)),
            "record": record.render_tile(self._rec_state, self._rec.seconds, self._rec.level),
        }

    def _body(self, which: str) -> str:
        if which == "focus":
            return focus.render_body(self.pomo)
        if which == "board":
            return board.render_body(self.board_data)
        if which == "record":
            return record.render_body(self._rec_state, self._rec.seconds,
                                      self._rec.level, self._last_transcript,
                                      self._auto_on, self._auto_min)
        return capture.render_body(capture.pick_prompt(self._prompt_i), self._last_saved)

    def _paint(self) -> None:
        tiles = self._tiles()
        self.query_one("#tile-board", Static).update(tiles["board"])
        self.query_one("#tile-focus", Static).update(tiles["focus"])
        self.query_one("#tile-capture", Static).update(tiles["capture"])
        self.query_one("#tile-record", Static).update(tiles["record"])
        self.query_one("#clock", Static).update(f"[dim]{self.clock}[/dim]")
        for name, wid in (("board", "#tile-board"), ("focus", "#tile-focus"),
                          ("capture", "#tile-capture"), ("record", "#tile-record")):
            w = self.query_one(wid, Static)
            (w.add_class if self.mode == name else w.remove_class)("active-tile")
        if self.mode in PANELS:
            self.query_one("#stage-body", Static).update(self._body(self.mode))
        self._paint_hints()

    def _paint_hints(self) -> None:
        """Re-render the key legend for the current mode at the current width.
        Called on every paint and on resize, so it always fits and always
        reflects the open panel."""
        width = self.size.width or 80          # size is (0,0) before first layout
        self.query_one("#hints", Static).update(hints.render(self.mode, width - 2))

    def on_resize(self, event) -> None:
        self._paint_hints()


def main() -> None:
    Deck().run()


if __name__ == "__main__":
    main()
