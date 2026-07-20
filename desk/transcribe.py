"""Transcribe a 16 kHz mono WAV with faster-whisper — local, offline, CPU. The
model downloads once (~150 MB for 'base'). Optional deps (faster-whisper, numpy)
are lazy-imported inside the functions, so importing this module is cheap and
never slows desk startup or breaks a core-only install.
"""
from __future__ import annotations

import importlib.util
import os
import wave
from pathlib import Path

# ctranslate2's OpenMP runtime clashes with conda/MKL's; this is the standard,
# inference-safe workaround. Harmless on a clean (non-conda) machine.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

DEFAULT_MODEL = "base"
AVAILABLE = all(importlib.util.find_spec(m) for m in ("numpy", "faster_whisper"))

_model_cache: dict[str, object] = {}


def _read_wav_16k(path: Path):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0


def _load(model_size: str):
    from faster_whisper import WhisperModel
    if model_size not in _model_cache:
        _model_cache[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _model_cache[model_size]


def transcribe(wav: Path, model_size: str = DEFAULT_MODEL,
               language: str | None = None) -> str:
    """Return the transcript text for a 16 kHz mono WAV. Raises RuntimeError if
    the optional extra is missing. Empty audio -> empty string."""
    if not AVAILABLE:
        raise RuntimeError("transcription needs the optional extra: pip install desk[record]")
    data = _read_wav_16k(wav)
    if data.size == 0:
        return ""
    model = _load(model_size)
    segments, _info = model.transcribe(data, language=language, beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()


def save_transcript(wav: Path, text: str, now=None) -> Path:
    """Write transcript.md beside the audio, with a dated header. Returns path."""
    from datetime import datetime
    now = now or datetime.now()
    out = wav.parent / "transcript.md"
    body = text.strip() if text.strip() else "_(no speech detected)_"
    out.write_text(f"# Transcript — {now:%Y-%m-%d %H:%M}\n\n{body}\n", encoding="utf-8")
    return out
