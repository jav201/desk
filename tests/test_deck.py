"""Shell tests: the deck boots compact, expands/collapses each panel, and the
capture Input does NOT steal the panel hotkeys (the bug the prototype exposed)."""
from __future__ import annotations

from desk.app import Deck, PANELS


async def test_boots_compact():
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.mode == "strip"
        assert "hidden" in app.query_one("#stage").classes


async def test_expand_each_panel_then_collapse():
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        for key, name in (("b", "board"), ("f", "focus"), ("c", "capture")):
            await pilot.press(key)
            await pilot.pause()
            assert app.mode == name, (key, app.mode)
            assert "hidden" not in app.query_one("#stage").classes
            await pilot.press("escape")
            await pilot.pause()
            assert app.mode == "strip"


async def test_hotkeys_survive_the_capture_input():
    """WHY: a focusable Input in the tree silently swallows single-key hotkeys.
    If this regresses, `f` from rest would type into the box instead of opening
    Focus. Guarded by can_focus=False (off) + priority bindings."""
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")                      # must open Focus, not type 'f'
        await pilot.pause()
        assert app.mode == "focus"
        await pilot.press("c")                       # capture focuses the input
        await pilot.pause()
        inp = app.query_one("#cap-input")
        assert inp.display is True
        assert app.focused is inp


async def test_every_panel_has_a_placeholder_body():
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        for name in PANELS:
            app.action_expand(name)
            await pilot.pause()
            body = str(app.query_one("#stage-body").render())
            assert name.upper() in body.upper()


def test_deck_disables_auto_focus():
    """Root-cause guard: Textual's default AUTO_FOCUS='*' auto-focuses the
    capture Input at mount, which swallows the global hotkeys until an esc frees
    it — the 'ribbon shows but nothing works until I press esc' bug. Pilot's
    mount timing hides it, so a behavioural test would be vacuous; pin the fix
    itself. If this is ever reverted the bug returns."""
    assert Deck.AUTO_FOCUS is None


async def test_auto_focus_star_would_grab_a_composed_input():
    """Documents WHY the guard above matters: an Input composed under the default
    AUTO_FOCUS='*' really does get auto-focused, so leaving it default would
    reintroduce the swallow-the-keys bug. This is the mechanism, on a minimal app
    so it doesn't depend on desk's own mount-timing luck."""
    from textual.app import App, ComposeResult
    from textual.widgets import Input, Static

    class Mini(App):
        AUTO_FOCUS = "*"
        def compose(self) -> ComposeResult:
            yield Static("x")
            yield Input()

    app = Mini()
    async with app.run_test(size=(40, 6)) as pilot:
        await pilot.pause()
        assert isinstance(app.focused, Input)          # * grabs it — desk must not


async def test_startup_hotkey_fires_without_any_warmup(tmp_path, monkeypatch):
    """A hotkey must work on the very first keypress — no keys+esc warmup."""
    from desk import board
    monkeypatch.setattr(board, "BOARD_PATH", tmp_path / "nope.json")
    app = Deck()
    async with app.run_test(size=(90, 16)) as pilot:
        await pilot.pause()
        assert app.focused is None                     # nothing grabbed focus
        await pilot.press("f")                         # first keypress
        await pilot.pause()
        assert app.mode == "focus"


async def test_leaving_capture_releases_focus_so_hotkeys_live():
    """Regression: escaping Capture used to leave focus stuck on the hidden
    Input, which intermittently swallowed the global hotkeys ('a veces'). After
    collapse the app must have NO focused widget, and a hotkey must fire again."""
    from textual.widgets import Input
    app = Deck()
    async with app.run_test(size=(90, 16)) as pilot:
        await pilot.pause()
        await pilot.press("c")                         # open capture
        await pilot.pause()
        assert app.focused is app.query_one("#cap-input", Input)
        await pilot.press("escape")                    # leave it
        await pilot.pause()
        assert app.focused is None                     # focus deterministically released
        await pilot.press("f")                         # a global hotkey works again
        await pilot.pause()
        assert app.mode == "focus"


async def test_switching_panels_never_leaves_input_focused():
    """Any panel reached without going through Capture must not hold the Input."""
    from textual.widgets import Input
    app = Deck()
    async with app.run_test(size=(90, 16)) as pilot:
        await pilot.pause()
        inp = app.query_one("#cap-input", Input)
        for key, mode in (("f", "focus"), ("b", "board"), ("m", "record")):
            await pilot.press(key)
            await pilot.pause()
            assert app.mode == mode
            assert app.focused is not inp              # input never steals these
        await pilot.press("escape")
        await pilot.pause()
        assert app.mode == "strip" and app.focused is None


async def test_hint_bar_shows_keys_and_follows_the_open_panel():
    """The legend must exist, keep quit visible in a NARROW window (Textual's
    Footer dropped it at 80 cols), and change when a panel opens."""
    import re
    app = Deck()
    async with app.run_test(size=(56, 16)) as pilot:
        await pilot.pause()
        bar = app.query_one("#hints")
        strip_text = re.sub(r"\[/?[^\]]*\]", "", str(bar.render()))
        assert "quit" in strip_text                    # never dropped, even narrow
        assert len(strip_text) <= 56                   # fits the window
        await pilot.press("f")                         # open the Focus panel
        await pilot.pause()
        focus_text = re.sub(r"\[/?[^\]]*\]", "", str(bar.render()))
        assert focus_text != strip_text                # the bar actually updates
        assert "start/pause" in focus_text and "esc" in focus_text


async def test_pomodoro_count_keys(tmp_path, monkeypatch):
    from desk import focus
    monkeypatch.setattr(focus, "STATE_PATH", tmp_path / "s.json")
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        base = app.pomo.target
        await pilot.press("plus")
        await pilot.pause()
        assert app.pomo.target == base + 1
        await pilot.press("minus")
        await pilot.press("minus")
        await pilot.pause()
        assert app.pomo.target == base - 1


async def test_open_board_spawns_terminal(monkeypatch):
    calls = []
    monkeypatch.setattr("shutil.which", lambda n: "wezterm")
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: calls.append((a, k)) or None)
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
    assert calls and "taskboard" in str(calls[0])


async def test_open_transcripts_opens_folder(tmp_path, monkeypatch):
    """'t' opens the transcripts folder in the OS file manager, creating it on
    demand so the key always works (win32: os.startfile; else: xdg-open/open)."""
    from desk import record
    tdir = tmp_path / "transcripts"
    monkeypatch.setattr(record, "TRANSCRIPTS_DIR", tdir)
    opened = []
    monkeypatch.setattr("os.startfile", lambda p: opened.append(p), raising=False)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: opened.append(a) or None)
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
    assert opened and str(tdir) in str(opened[0])
    assert tdir.is_dir()                     # created on demand


async def test_record_panel_opens():
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        assert app.mode == "record"
        assert "RECORD" in str(app.query_one("#stage-body").render())


async def test_record_toggle_unavailable_does_not_start(monkeypatch):
    from desk import record
    monkeypatch.setattr(record, "AVAILABLE", False)
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        await pilot.press("space")            # primary -> _rec_toggle, but unavailable
        await pilot.pause()
        assert app._rec_state == "idle"


async def test_record_start_sets_recording(monkeypatch):
    from desk import record

    class FakeRec:
        def __init__(self, *a, **k):
            self.running = False; self.seconds = 0.0; self.level = 0.0
        def start(self): self.running = True
        def stop(self): self.running = False; return None

    monkeypatch.setattr(record, "AVAILABLE", True)
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._rec = FakeRec()
        await pilot.press("m")
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert app._rec_state == "recording" and app._rec.running is True


async def test_auto_toggle_key_in_record(tmp_path, monkeypatch):
    from desk import record
    monkeypatch.setattr(record, "RECORD_SETTINGS_PATH", tmp_path / "record.json")
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        before = app._auto_on
        await pilot.press("a")
        await pilot.pause()
        assert app._auto_on is (not before)


async def test_auto_adjust_keys_in_record(tmp_path, monkeypatch):
    from desk import record
    monkeypatch.setattr(record, "RECORD_SETTINGS_PATH", tmp_path / "record.json")
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        base = app._auto_min
        await pilot.press("plus")
        await pilot.pause()
        assert app._auto_min == base + record.AUTO_STEP
        await pilot.press("minus"); await pilot.press("minus")
        await pilot.pause()
        assert app._auto_min == base - record.AUTO_STEP


async def test_plus_minus_still_pomodoro_in_focus(tmp_path, monkeypatch):
    from desk import focus, record
    monkeypatch.setattr(focus, "STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(record, "RECORD_SETTINGS_PATH", tmp_path / "r.json")
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        base = app.pomo.target
        await pilot.press("plus")
        await pilot.pause()
        assert app.pomo.target == base + 1


async def test_autostop_triggers_stop(tmp_path, monkeypatch):
    from desk import record
    monkeypatch.setattr(record, "RECORD_SETTINGS_PATH", tmp_path / "record.json")
    monkeypatch.setattr(record, "AVAILABLE", True)

    class FakeRec:
        def __init__(self, *a, **k):
            self.running = False; self.seconds = 0.0; self.level = 0.0
        def start(self): self.running = True
        def stop(self): self.running = False; return None

    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._rec = FakeRec(); app._auto_on = True; app._auto_min = 1
        await pilot.press("m"); await pilot.pause()
        await pilot.press("space"); await pilot.pause()
        assert app._rec_state == "recording"
        app._rec.seconds = 61                     # past the 1-min threshold
        app._tick()                                # auto-stop should fire
        await pilot.pause()
        assert app._rec_state in ("transcribing", "idle")
