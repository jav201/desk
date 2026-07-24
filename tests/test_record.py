"""Recorder core: timestamp, WAV mix (sum, pad, clip, cleanup), and the
optional-extra guard. The live device capture is verified separately (needs real
audio hardware); these test the pure logic."""
from __future__ import annotations

import wave
from datetime import datetime

import numpy as np
import pytest

from desk import record


def _wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(record.SR)
        w.writeframes(np.asarray(samples, dtype="<i2").tobytes())


def _read(path):
    with wave.open(str(path), "rb") as w:
        return list(np.frombuffer(w.readframes(w.getnframes()), dtype="<i2"))


def test_stamp_format():
    assert record.stamp(datetime(2026, 7, 20, 3, 8, 29)) == "2026-07-20-030829"


def test_read_missing_is_empty(tmp_path):
    assert record._read_i32(tmp_path / "nope.wav").size == 0


def test_mix_sums_pads_and_cleans(tmp_path):
    a, b, out = tmp_path / "loopback.wav", tmp_path / "mic.wav", tmp_path / "audio.wav"
    _wav(a, [1000, 2000, 3000])
    _wav(b, [500, 500])                       # shorter -> zero-padded
    record._mix(a, b, out)
    assert _read(out) == [1500, 2500, 3000]
    assert not a.exists() and not b.exists()  # temp sources removed after mix


def test_mix_clips_to_int16(tmp_path):
    a, b, out = tmp_path / "loopback.wav", tmp_path / "mic.wav", tmp_path / "audio.wav"
    _wav(a, [30000]); _wav(b, [30000])        # 60000 -> clipped to 32767
    record._mix(a, b, out)
    assert _read(out) == [32767]


def test_start_requires_extra(monkeypatch, tmp_path):
    monkeypatch.setattr(record, "AVAILABLE", False)
    r = record.Recorder(base_dir=tmp_path)
    with pytest.raises(RuntimeError):
        r.start()


def test_fresh_recorder_not_running(tmp_path):
    r = record.Recorder(base_dir=tmp_path)
    assert r.running is False
    assert r.seconds == 0.0


def test_render_tile_states():
    assert "record a meeting" in record.render_tile("idle")
    assert "REC" in record.render_tile("recording", seconds=65)
    assert "01:05" in record.render_tile("recording", seconds=65)
    assert "transcrib" in record.render_tile("transcribing").lower()


def test_render_body_idle_shows_last_and_consent():
    body = record.render_body("idle", last="hello meeting world")
    assert "RECORD" in body
    assert "hello meeting world" in body
    assert "consent" in body


def test_render_body_recording_has_meter():
    body = record.render_body("recording", seconds=10, level=0.1)
    assert "recording" in body and "▊" in body


def test_settings_defaults_missing(tmp_path):
    assert record.load_settings(tmp_path / "nope.json") == {"enabled": True, "minutes": 60}


def test_settings_roundtrip_and_clamp(tmp_path):
    p = tmp_path / "record.json"
    record.save_settings(True, 30, p)
    assert record.load_settings(p) == {"enabled": True, "minutes": 30}
    record.save_settings(False, 9999, p)                 # out of range
    s = record.load_settings(p)
    assert s["enabled"] is False and s["minutes"] == record.AUTO_MIN_HI


def test_clamp_minutes():
    assert record.clamp_minutes(1) == record.AUTO_MIN_LO
    assert record.clamp_minutes(9999) == record.AUTO_MIN_HI
    assert record.clamp_minutes(45) == 45


def test_should_autostop():
    assert record.should_autostop(3600, True, 60) is True
    assert record.should_autostop(3599, True, 60) is False
    assert record.should_autostop(9999, False, 60) is False


def test_render_body_recording_autostop_countdown():
    body = record.render_body("recording", seconds=13 * 60, level=0.1,
                              auto_on=True, auto_min=60)
    assert "auto-stop in 47:00" in body
    assert "auto-stop: off" in record.render_body("recording", seconds=60, auto_on=False)


def test_render_body_idle_shows_setting():
    body = record.render_body("idle", auto_on=True, auto_min=45)
    assert "auto-stop" in body and "45 min" in body


def test_module_import_is_lazy_no_eager_audio_stack():
    """The launch-stall fix: importing desk.record must NOT import soundcard/numpy
    at module scope (soundcard init is what stalled desk startup). AVAILABLE stays
    a plain presence check."""
    assert isinstance(record.AVAILABLE, bool)
    assert not hasattr(record, "sc"), "soundcard imported at module scope (eager)"
    assert not hasattr(record, "np"), "numpy imported at module scope (eager)"


def test_render_body_idle_mentions_open_transcripts():
    assert "open transcripts folder" in record.render_body("idle")


def test_render_body_shows_whisper_device_indicator(monkeypatch):
    """The panel must tell the user whether transcription will run on the GPU or
    CPU (and the model), so 'is this using my card?' is answerable at a glance."""
    from desk import transcribe as T
    monkeypatch.setattr(T, "AVAILABLE", True)
    monkeypatch.setattr(T, "_active_device", None)
    monkeypatch.delenv("DESK_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr(record, "AVAILABLE", True)
    monkeypatch.setattr(T, "_cuda_cached", True)          # GPU present
    body = record.render_body("idle")
    assert "whisper:" in body and "GPU" in body
    monkeypatch.setattr(T, "_cuda_cached", False)         # no GPU
    assert "CPU" in record.render_body("idle")
    # the transcribing state also names the device instead of hard-coding "CPU"
    assert "CPU" in record.render_body("transcribing")
