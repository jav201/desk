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

PANELS = ("board", "focus", "capture")

# palette (kept here until the shared `desk` core is extracted in a later pass)
TOMATO = "#ff6347"
ACCENT = "#2dd4bf"


class Deck(App):
    """The always-on-top deck. `mode` is either "strip" (compact) or a panel."""

    CSS_PATH = "desk.tcss"

    BINDINGS = [
        # priority: fire even when the capture Input is focused
        Binding("b", "expand('board')", "Board", priority=True),
        Binding("f", "expand('focus')", "Focus", priority=True),
        Binding("c", "expand('capture')", "Capture", priority=True),
        Binding("escape", "collapse", "Strip", priority=True),
        ("q", "quit", "Quit"),
    ]

    mode = reactive("strip")
    clock = reactive("--:--:--")

    def compose(self) -> ComposeResult:
        with Horizontal(id="strip"):
            yield Static(id="tile-board", classes="tile")
            yield Static(id="tile-focus", classes="tile")
            yield Static(id="tile-capture", classes="tile")
            yield Static(id="clock")
        with Vertical(id="stage", classes="hidden"):
            yield Static(id="stage-body")
            yield Input(placeholder="type a thought, hit enter…", id="cap-input")

    def on_mount(self) -> None:
        inp = self.query_one("#cap-input", Input)
        inp.display = False
        inp.can_focus = False          # else it steals the b/f/c hotkeys at rest
        self._paint()
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        self.clock = datetime.now().strftime("%H:%M:%S")
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
        else:
            inp.display = False
            inp.can_focus = False
        self._paint()

    def action_collapse(self) -> None:
        self.mode = "strip"
        inp = self.query_one("#cap-input", Input)
        inp.display = False
        inp.can_focus = False
        self.query_one("#stage").add_class("hidden")
        self._paint()

    # ---- rendering (placeholder content until later increments) -----------
    def _tiles(self) -> dict[str, str]:
        """The minimized live tiles. Real data arrives with each panel's
        increment; for now they are honest placeholders."""
        return {
            "board": "› [dim](no board loaded)[/dim]",
            "focus": f"[{TOMATO}]|| 25:00[/]  [dim]○○○○○[/dim]",
            "capture": "[dim]› capture a thought…[/dim]",
        }

    def _body(self, which: str) -> str:
        title = {"board": "BOARD", "focus": "FOCUS", "capture": "CAPTURE"}[which]
        stub = {
            "board": "reads your taskboard board.json — arrives in increment 3",
            "focus": "braille pomodoro clock — arrives in increment 2",
            "capture": "rotating prompts + Obsidian daily note — arrives in increment 4",
        }[which]
        return f"[bold {ACCENT}]{title}[/]\n\n[dim]{stub}[/dim]"

    def _paint(self) -> None:
        tiles = self._tiles()
        self.query_one("#tile-board", Static).update(tiles["board"])
        self.query_one("#tile-focus", Static).update(tiles["focus"])
        self.query_one("#tile-capture", Static).update(tiles["capture"])
        self.query_one("#clock", Static).update(f"[dim]{self.clock}[/dim]")
        for name, wid in (("board", "#tile-board"), ("focus", "#tile-focus"),
                          ("capture", "#tile-capture")):
            w = self.query_one(wid, Static)
            (w.add_class if self.mode == name else w.remove_class)("active-tile")
        if self.mode in PANELS:
            self.query_one("#stage-body", Static).update(self._body(self.mode))


def main() -> None:
    Deck().run()


if __name__ == "__main__":
    main()
