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


def clipboard_text() -> str:
    """Best-effort read of the OS clipboard. Textual can't do this (it only
    WRITES, via OSC 52), so we ask the OS directly: ctypes on Windows (instant,
    no dependency), pyperclip if it happens to be installed, else the platform's
    paste command. Every path is guarded — if the clipboard can't be read we
    simply return "" and the prompt opens empty."""
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
            k32.GlobalLock.restype = ctypes.c_void_p      # else truncated on 64-bit
            k32.GlobalLock.argtypes = [ctypes.c_void_p]
            k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            u32.GetClipboardData.restype = ctypes.c_void_p
            if not u32.OpenClipboard(0):
                return ""
            try:
                handle = u32.GetClipboardData(13)         # CF_UNICODETEXT
                if not handle:
                    return ""
                ptr = k32.GlobalLock(handle)
                try:
                    return ctypes.c_wchar_p(ptr).value or ""
                finally:
                    k32.GlobalUnlock(handle)
            finally:
                u32.CloseClipboard()
        except Exception:
            return ""
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except Exception:
        pass
    try:
        import subprocess
        cmd = (["pbpaste"] if sys.platform == "darwin"
               else ["xclip", "-selection", "clipboard", "-o"])
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=2).stdout or ""
    except Exception:
        return ""


def clipboard_url() -> str | None:
    """The clipboard's contents IF they are an http(s) link, else None. Read
    once when the prompt opens — never polled, and never sent anywhere."""
    from . import fetch
    try:
        text = (clipboard_text() or "").strip().split("\n")[0].strip()
    except Exception:
        return None
    return text if fetch.is_url(text) else None


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
            yield Input(placeholder="paste a path or a video URL, or browse below…",
                        id="pick-path")
            yield Label("transcribe a file", id="pick-body")   # on_mount fills it

    def on_mount(self) -> None:
        self._reload()
        self.query_one("#pick-path", Input).focus()

    def _reload(self) -> None:
        self.entries = list_dir(self.cwd)
        self.idx = max(0, min(self.idx, len(self.entries) - 1))
        self._repaint()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Typing/pasting a URL swaps the folder browser for a link card — the
        browser is meaningless for a URL, and the swap is the signal that desk
        understood what was pasted."""
        self._repaint()

    def _link_card(self, url: str) -> list[str]:
        from . import fetch
        host = url.split("/")[2] if url.count("/") >= 2 else url
        lines = [f"[bold #2dd4bf]transcribe a web video[/]  [dim]{_fit(host, 30)}[/dim]",
                 "", f"[#2dd4bf]◆[/] [#dbe4ee]{_fit(url, 46)}[/]", ""]
        if fetch.AVAILABLE:
            lines += ["[dim]Enter fetches the audio and transcribes it[/dim]",
                      "[dim]audio only · transcribed locally · max 2 h[/dim]"]
        else:
            lines += ["[#ff8c42]not enabled[/] [dim]— pip install desk\\[web][/dim]"]
        return lines + ["", "[dim]Esc cancel[/dim]"]

    def _repaint(self) -> None:
        try:
            typed = self.query_one("#pick-path", Input).value.strip()
        except Exception:
            typed = ""
        from . import fetch
        if fetch.is_url(typed):                      # a URL: show the link card
            self.query_one("#pick-body", Label).update("\n".join(self._link_card(typed)))
            return
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
        from . import fetch
        text = event.value.strip()
        if fetch.is_url(text):                       # a URL: hand it back as a str
            if not fetch.AVAILABLE:
                self.notify("web video needs: pip install desk[web]", severity="warning")
                return
            self.dismiss(text)
        elif text:                                   # a typed/pasted path
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


class UrlPrompt(ModalScreen):
    """A one-line prompt for a video URL (the `u` key). Dismisses with the URL
    string, or None on Esc. Rejects anything that isn't http(s) in place, so a
    `file://` never reaches the downloader.

    If the clipboard already holds a link when the prompt opens — which is the
    normal case, since you copy a URL and THEN press `u` — it is offered as the
    placeholder: shown dimmed, replaced the moment you type, and used only if
    you press Enter on an empty box. It is never auto-submitted and never
    leaves the machine.
    """

    def __init__(self, suggestion: str | None = None):
        super().__init__()
        # None = read the clipboard on mount; a value = use it (also lets tests
        # exercise the flow without touching the real clipboard)
        self._suggestion = suggestion

    def compose(self):
        with VerticalScroll(id="pick-box", classes="pick"):
            yield Input(placeholder="https://…  (YouTube and ~1800 other sites)",
                        id="url-input")
            yield Label("x", id="url-note")           # filled on mount

    def on_mount(self) -> None:
        if self._suggestion is None:
            self._suggestion = clipboard_url()
        inp = self.query_one("#url-input", Input)
        if self._suggestion:
            inp.placeholder = self._suggestion        # dim, replaced by typing
            self._note(f"[#2dd4bf]◆[/] [dim]found this link on the clipboard[/dim]",
                       keys="Enter fetches it · type replaces · Esc cancel")
        else:
            self._note("[dim]audio only · transcribed locally · max 2 h[/dim]")
        inp.focus()

    def _note(self, markup: str, keys: str = "Enter fetch · Esc cancel") -> None:
        self.query_one("#url-note", Label).update(
            f"[bold #2dd4bf]transcribe a web video[/]\n\n{markup}\n\n"
            f"[dim]{keys}[/dim]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        from . import fetch
        # empty box + a clipboard suggestion -> accept the suggestion (never auto)
        url = event.value.strip() or (self._suggestion or "")
        if not fetch.is_url(url):
            # the same rule fetch.py enforces — stated here so the user sees WHY
            self._note("[#ff3b30]only http(s) links are supported[/]")
            return
        if not fetch.AVAILABLE:
            self._note("[#ff8c42]not enabled[/] [dim]— pip install desk\\[web][/dim]")
            return
        self.dismiss(url)
