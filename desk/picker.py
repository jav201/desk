"""In-app audio picker for the Record panel: choose an EXISTING audio file to
transcribe. Combines a paste/type path input with an arrow-key folder browser.

The listing/resolving logic is pure (no UI) so it's fully testable; the modal is
a thin Textual shell over it. Picking a file dismisses with its Path; the app
then runs the same GPU-or-CPU `transcribe_file` in a worker.
"""
from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label

# what faster-whisper (PyAV) can decode — and what the browser lists.
AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac",
              ".m4b", ".wma", ".webm", ".mp4", ".mkv", ".mov"}
_ROWS = 12                                   # visible browser rows


def is_audio(p: Path) -> bool:
    return p.suffix.lower() in AUDIO_EXTS


def list_dir(path: Path) -> list[Path]:
    """Browser entries for `path`: a parent '..' (unless already at a root), then
    subdirectories, then audio files — each group sorted case-insensitively.
    Never raises: an unreadable directory yields just the parent entry."""
    try:
        kids = list(path.iterdir())
    except OSError:
        kids = []
    dirs = sorted((p for p in kids if p.is_dir()), key=lambda q: q.name.lower())
    files = sorted((p for p in kids if p.is_file() and is_audio(p)),
                   key=lambda q: q.name.lower())
    out: list[Path] = []
    if path.parent != path:                  # not a filesystem root -> offer '..'
        out.append(path.parent)
    return out + dirs + files


def resolve_input(text: str, cwd: Path) -> Path | None:
    """Turn a typed/pasted string into an existing path: ~ is expanded, a
    relative path is taken against `cwd`, surrounding quotes are stripped.
    Returns None when it points at nothing that exists."""
    text = text.strip().strip('"').strip("'")
    if not text:
        return None
    p = Path(text).expanduser()
    if not p.is_absolute():
        p = cwd / p
    try:
        p = p.resolve()
    except OSError:
        return None
    return p if p.exists() else None


def _fit(s: str, w: int) -> str:
    return s if len(s) <= w else "…" + s[-(w - 1):]


class AudioPicker(ModalScreen):
    """Paste a path (Enter) OR browse with ↑/↓ + Enter. Enter on a folder
    descends into it; Enter on an audio file — or a valid pasted file path —
    dismisses with that Path. Escape cancels (dismiss None)."""

    # escape is handled by the deck (action_collapse closes the top modal), so
    # it doesn't need a binding here; only the browser keys do.
    BINDINGS = [
        Binding("up", "move(-1)", "Up"),
        Binding("down", "move(1)", "Down"),
    ]

    def __init__(self, start: Path | None = None):
        super().__init__()
        try:
            self.cwd = (start or Path.home()).resolve()
        except OSError:
            self.cwd = Path.home()
        self.entries: list[Path] = []
        self.idx = 0

    def compose(self):
        with VerticalScroll(id="pick-box", classes="pick"):
            yield Input(placeholder="paste a path, or browse below (up/down, Enter)…",
                        id="pick-path")
            yield Label("transcribe a file", id="pick-body")   # on_mount fills it

    def on_mount(self) -> None:
        self._reload()
        self.query_one("#pick-path", Input).focus()

    def _reload(self) -> None:
        self.entries = list_dir(self.cwd)
        self.idx = max(0, min(self.idx, len(self.entries) - 1))
        self._repaint()

    def _repaint(self) -> None:
        head = f"[bold #2dd4bf]transcribe a file[/]  [dim]{_fit(str(self.cwd), 42)}[/dim]"
        lines = [head, ""]
        lo = max(0, min(self.idx - _ROWS // 2, max(0, len(self.entries) - _ROWS)))
        for i in range(lo, min(lo + _ROWS, len(self.entries))):
            p = self.entries[i]
            if i == 0 and p == self.cwd.parent:
                icon, label, color = "..", "", "#ffd166"
                text = ".."
            elif p.is_dir():
                icon, text, color = ">", p.name + "/", "#38bdf8"
            else:
                icon, text, color = "-", p.name, "#3fb950"
            body = f"{icon} {_fit(text, 40)}" if p != self.cwd.parent else ".."
            lines.append(f"[on #1b2735] [{color}]{body}[/] [/]" if i == self.idx
                         else f"  [{color}]{body}[/]")
        if not self.entries:
            lines.append("[dim](nothing to show here)[/dim]")
        lines += ["", "[dim]up/down move . Enter open/pick . Esc cancel[/dim]"]
        self.query_one("#pick-body", Label).update("\n".join(lines))

    def action_move(self, delta: int) -> None:
        if self.entries:
            self.idx = max(0, min(len(self.entries) - 1, self.idx + delta))
            self._repaint()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:                                     # a typed/pasted path wins
            p = resolve_input(text, self.cwd)
            if p is None:
                self.notify("no such file or folder", severity="error")
                return
            self._activate(p)
        elif self.entries:                           # empty box -> act on the selection
            self._activate(self.entries[self.idx])

    def _activate(self, p: Path) -> None:
        if p.is_dir():
            self.cwd = p
            self.idx = 0
            self.query_one("#pick-path", Input).value = ""
            self._reload()
        elif is_audio(p):
            self.dismiss(p)
        else:
            self.notify("not an audio file", severity="warning")
