"""transcribe_file() + the `desk-transcribe` CLI: path is handed straight to
faster-whisper (any format, mocked model), segments join, the optional-extra
guard, and per-file <name>.md writing. The real model is verified on-device."""
from __future__ import annotations

import pytest

from desk import transcribe as T


class _Seg:
    def __init__(self, text): self.text = text


def test_transcribe_file_passes_path_and_joins(tmp_path, monkeypatch):
    seen = {}

    class FakeModel:
        def transcribe(self, audio, language=None, beam_size=1):
            seen["audio"] = audio
            seen["language"] = language
            return [_Seg("  hola "), _Seg(" mundo  ")], None

    monkeypatch.setattr(T, "AVAILABLE", True)
    monkeypatch.setattr(T, "_load", lambda ms: FakeModel())
    clip = tmp_path / "clip.m4a"
    clip.write_bytes(b"not-real-audio")

    assert T.transcribe_file(clip, language="es") == "hola mundo"
    # the raw path is passed through — faster-whisper decodes m4a itself
    assert seen["audio"] == str(clip) and seen["language"] == "es"


def test_transcribe_file_requires_extra(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "AVAILABLE", False)
    with pytest.raises(RuntimeError):
        T.transcribe_file(tmp_path / "a.m4a")


def test_main_writes_md_beside_each(tmp_path, monkeypatch):
    a = tmp_path / "a.m4a"; a.write_bytes(b"x")
    b = tmp_path / "b.mp3"; b.write_bytes(b"y")
    monkeypatch.setattr(T, "AVAILABLE", True)
    monkeypatch.setattr(T, "transcribe_file",
                        lambda p, model_size=None, language=None: f"text of {p.name}")

    T.main([str(a), str(b)])

    ta = (tmp_path / "a.md").read_text(encoding="utf-8")
    tb = (tmp_path / "b.md").read_text(encoding="utf-8")
    assert "# Transcript — a.m4a" in ta and "text of a.m4a" in ta
    assert "# Transcript — b.mp3" in tb and "text of b.mp3" in tb


def test_main_skips_missing_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(T, "AVAILABLE", True)
    monkeypatch.setattr(T, "transcribe_file",
                        lambda p, model_size=None, language=None: "unused")

    T.main([str(tmp_path / "ghost.m4a")])

    assert "skip (not found)" in capsys.readouterr().out
    assert not (tmp_path / "ghost.md").exists()


def test_main_requires_extra(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "AVAILABLE", False)
    with pytest.raises(SystemExit):
        T.main([str(tmp_path / "a.m4a")])
