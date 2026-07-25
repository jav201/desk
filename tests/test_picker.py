"""Audio picker: the pure listing/resolving logic, and the in-app flow —
pressing `i` opens the modal, browsing filters to audio, and picking a file
transcribes it beside the source. The live recording path is untouched."""
from __future__ import annotations

from pathlib import Path

from desk import picker
from desk.app import Deck
from desk.picker import AudioPicker


# ---- pure logic -------------------------------------------------------------
def test_is_audio_by_extension():
    assert picker.is_audio(Path("a.M4A")) and picker.is_audio(Path("x/y.mp3"))
    assert not picker.is_audio(Path("notes.txt")) and not picker.is_audio(Path("d/"))


def test_list_dir_shows_dirs_then_audio_and_a_parent(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "b.mp3").write_bytes(b"x")
    (tmp_path / "a.wav").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")     # non-audio -> hidden
    names = [p.name for p in picker.list_dir(tmp_path)]
    assert names[0] == tmp_path.parent.name       # '..' parent first
    assert names[1] == "sub"                       # dirs before files
    assert names[2:] == ["a.wav", "b.mp3"]         # audio only, sorted; .txt gone


def test_list_dir_at_root_has_no_parent_entry():
    root = Path(Path.cwd().anchor)                  # e.g. C:\ — its own parent
    assert root.parent == root
    assert all(p != root for p in picker.list_dir(root))   # no self-pointing '..'


def test_resolve_input_paths(tmp_path):
    f = tmp_path / "clip.m4a"
    f.write_bytes(b"x")
    assert picker.resolve_input(f'"{f}"', tmp_path) == f.resolve()   # quotes stripped
    assert picker.resolve_input("clip.m4a", tmp_path) == f.resolve()  # relative to cwd
    assert picker.resolve_input("nope.m4a", tmp_path) is None         # missing -> None
    assert picker.resolve_input("   ", tmp_path) is None              # blank -> None


# ---- in-app flow ------------------------------------------------------------
async def test_i_opens_picker_and_escape_cancels(monkeypatch):
    from desk import transcribe
    monkeypatch.setattr(transcribe, "AVAILABLE", True)
    app = Deck()
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.action_expand("record")
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, AudioPicker)          # modal opened
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, AudioPicker)      # escape cancelled it


async def test_picker_browses_filters_and_picks(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    app = Deck()
    got = {}
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause()
        app.push_screen(AudioPicker(start=tmp_path), lambda r: got.update(res=r))
        await pilot.pause()
        pk = app.screen
        names = [p.name for p in pk.entries]
        assert "a.mp3" in names and "notes.txt" not in names   # audio-only browse
        i0 = pk.idx
        await pilot.press("down")
        await pilot.pause()
        assert pk.idx == i0 + 1                                 # ↑/↓ moves selection
        # select the audio file and pick it (empty input -> acts on selection)
        pk.idx = names.index("a.mp3")
        await pilot.press("enter")
        await pilot.pause()
        assert got["res"] == (tmp_path / "a.mp3").resolve()     # dismissed with the file


async def test_picked_file_is_transcribed_beside_source(tmp_path, monkeypatch):
    from desk import transcribe
    monkeypatch.setattr(transcribe, "AVAILABLE", True)
    monkeypatch.setattr(transcribe, "transcribe_file",
                        lambda p, **k: "the meeting words")
    audio = tmp_path / "call.mp3"
    audio.write_bytes(b"x")
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        # the worker normally runs off-thread; call it inline with a direct
        # call_from_thread so the assertion sees the finished state.
        monkeypatch.setattr(app, "call_from_thread", lambda fn, *a, **k: fn(*a, **k))
        app._run_file_transcription(audio)          # the worker body
        await pilot.pause()
        md = audio.with_suffix(".md")
        assert md.exists()
        text = md.read_text(encoding="utf-8")
        assert "# Transcript — call.mp3" in text and "the meeting words" in text


async def test_transcribe_file_action_guarded_when_busy(monkeypatch):
    """Kicking off a file transcription must not clobber an in-progress job."""
    from desk import transcribe
    monkeypatch.setattr(transcribe, "AVAILABLE", True)
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._rec_state = "recording"
        app.action_transcribe_file()
        await pilot.pause()
        assert not isinstance(app.screen, AudioPicker)   # refused while busy
