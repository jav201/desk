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
