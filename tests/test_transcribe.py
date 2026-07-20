"""Transcription: WAV read, segment-join (mocked model), transcript.md writing,
and the optional-extra guard. The real model is verified separately (on-device)."""
from __future__ import annotations

import wave
from datetime import datetime

import numpy as np
import pytest

from desk import transcribe as T


def _wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(np.asarray(samples, dtype="<i2").tobytes())


def test_read_wav_16k_normalises(tmp_path):
    p = tmp_path / "a.wav"
    _wav(p, [0, 32767, -32768])
    data = T._read_wav_16k(p)
    assert data.dtype == np.float32
    assert abs(data[1] - 1.0) < 1e-3 and data[0] == 0.0


def test_transcribe_joins_segments(tmp_path, monkeypatch):
    p = tmp_path / "a.wav"
    _wav(p, [0] * 1600)

    class Seg:
        def __init__(self, t): self.text = t

    class FakeModel:
        def transcribe(self, data, language=None, beam_size=1):
            return [Seg("  hello "), Seg(" world  ")], None

    monkeypatch.setattr(T, "AVAILABLE", True)
    monkeypatch.setattr(T, "_load", lambda ms: FakeModel())
    assert T.transcribe(p) == "hello world"


def test_transcribe_empty_audio_is_blank(tmp_path, monkeypatch):
    p = tmp_path / "a.wav"
    _wav(p, [])
    monkeypatch.setattr(T, "AVAILABLE", True)
    monkeypatch.setattr(T, "_load", lambda ms: (_ for _ in ()).throw(AssertionError("model must not load for empty audio")))
    assert T.transcribe(p) == ""


def test_transcribe_requires_extra(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "AVAILABLE", False)
    with pytest.raises(RuntimeError):
        T.transcribe(tmp_path / "a.wav")


def test_save_transcript_writes_md(tmp_path):
    wav = tmp_path / "audio.wav"
    out = T.save_transcript(wav, "the meeting transcript", now=datetime(2026, 7, 20, 3, 8))
    assert out == tmp_path / "transcript.md"
    text = out.read_text(encoding="utf-8")
    assert "# Transcript — 2026-07-20 03:08" in text and "the meeting transcript" in text


def test_save_transcript_empty_marks_no_speech(tmp_path):
    out = T.save_transcript(tmp_path / "audio.wav", "   ", now=datetime(2026, 7, 20, 3, 8))
    assert "_(no speech detected)_" in out.read_text(encoding="utf-8")
