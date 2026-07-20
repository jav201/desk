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
