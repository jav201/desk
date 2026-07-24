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


def test_resolve_device_respects_explicit_env(monkeypatch):
    """DESK_WHISPER_DEVICE forces the backend regardless of what's present."""
    monkeypatch.setattr(T, "_cuda_cached", False)          # even with no GPU seen
    monkeypatch.delenv("DESK_WHISPER_COMPUTE", raising=False)
    monkeypatch.setenv("DESK_WHISPER_DEVICE", "cpu")
    assert T._resolve_device() == ("cpu", "int8")
    monkeypatch.setenv("DESK_WHISPER_DEVICE", "cuda")
    assert T._resolve_device() == ("cuda", "float16")


def test_auto_device_follows_gpu_presence(monkeypatch):
    """The default ('auto') picks the GPU when present, CPU otherwise — this is
    what keeps one build fast on a GPU box and portable on a laptop."""
    monkeypatch.delenv("DESK_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr(T, "_cuda_cached", True)
    assert T.planned_device() == "cuda"
    monkeypatch.setattr(T, "_cuda_cached", False)
    assert T.planned_device() == "cpu"


def test_compute_type_override(monkeypatch):
    monkeypatch.delenv("DESK_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr(T, "_cuda_cached", True)
    monkeypatch.setenv("DESK_WHISPER_COMPUTE", "int8_float16")
    assert T._resolve_device() == ("cuda", "int8_float16")


def test_load_falls_back_to_cpu_when_gpu_unusable(monkeypatch):
    """A GPU that is detected but can't build a model (driver/cuDNN mismatch, OOM)
    must NOT crash transcription — it falls back to CPU, and active_device says so.
    Without this, an in-app transcription would blow up on a half-configured box."""
    import sys
    import types
    seen = []

    class FakeModel:
        def __init__(self, size, device, compute_type):
            seen.append(device)
            if device == "cuda":
                raise RuntimeError("cuda unusable")

    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    monkeypatch.setattr(T, "_model_cache", {})
    monkeypatch.setattr(T, "_active_device", None)
    monkeypatch.setattr(T, "_cuda_cached", True)           # auto -> tries cuda first
    monkeypatch.delenv("DESK_WHISPER_DEVICE", raising=False)
    T._load("base")
    assert seen == ["cuda", "cpu"]                         # tried GPU, then fell back
    assert T.active_device() == "cpu"


def test_load_stays_on_gpu_when_it_builds(monkeypatch):
    import sys
    import types

    class FakeModel:
        def __init__(self, size, device, compute_type):
            self.device = device

    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    monkeypatch.setattr(T, "_model_cache", {})
    monkeypatch.setattr(T, "_active_device", None)
    monkeypatch.setattr(T, "_cuda_cached", True)
    monkeypatch.delenv("DESK_WHISPER_DEVICE", raising=False)
    T._load("base")
    assert T.active_device() == "cuda"


def test_device_label_reflects_device_and_availability(monkeypatch):
    monkeypatch.delenv("DESK_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr(T, "AVAILABLE", True)
    monkeypatch.setattr(T, "_active_device", None)
    monkeypatch.setattr(T, "_cuda_cached", True)
    assert T.device_label().endswith("· GPU")
    monkeypatch.setattr(T, "_cuda_cached", False)
    assert T.device_label().endswith("· CPU")
    monkeypatch.setattr(T, "AVAILABLE", False)
    assert "install" in T.device_label()


def test_default_model_env_override(monkeypatch):
    """DESK_WHISPER_MODEL overrides the model — a Hub name OR a local dir path
    (for offline/locked-down boxes). Unset -> the Hub 'base' default."""
    import importlib
    monkeypatch.setenv("DESK_WHISPER_MODEL", r"C:\models\faster-whisper-base")
    importlib.reload(T)
    assert T.DEFAULT_MODEL == r"C:\models\faster-whisper-base"
    monkeypatch.delenv("DESK_WHISPER_MODEL", raising=False)
    importlib.reload(T)                       # restore module state for other tests
    assert T.DEFAULT_MODEL == "base"
