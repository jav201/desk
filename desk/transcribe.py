"""Transcribe a 16 kHz mono WAV with faster-whisper — local and offline. Runs on
the GPU when one is present (auto-detected) and falls back to CPU otherwise, so
the same build stays portable. The model downloads once (~150 MB for 'base').
Optional deps (faster-whisper, numpy) are lazy-imported inside the functions, so
importing this module is cheap and never slows desk startup or a core-only install.
"""
from __future__ import annotations

import importlib.util
import os
import wave
from pathlib import Path

# ctranslate2's OpenMP runtime clashes with conda/MKL's; this is the standard,
# inference-safe workaround. Harmless on a clean (non-conda) machine.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# A Hub model name ("base", "tiny.en", …) OR a local directory path. Set
# DESK_WHISPER_MODEL to a folder containing config.json/model.bin/… to load a
# pre-fetched model with zero network calls — for locked-down / offline boxes
# where huggingface.co is blocked. Default keeps the Hub "base" model.
DEFAULT_MODEL = os.environ.get("DESK_WHISPER_MODEL", "base")
AVAILABLE = all(importlib.util.find_spec(m) for m in ("numpy", "faster_whisper"))

_CPU_COMPUTE = "int8"          # widely supported, low memory
_GPU_COMPUTE = "float16"       # what CUDA WhisperModels expect

_model_cache: dict[str, object] = {}
_cuda_cached: bool | None = None      # memoized GPU probe (won't change mid-session)
_active_device: str | None = None     # device a model actually loaded on


def _read_wav_16k(path: Path):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0


def _cuda_available() -> bool:
    """True when CTranslate2 (faster-whisper's backend) sees a CUDA device.
    Memoized and defensive: any import/probe failure counts as no GPU."""
    global _cuda_cached
    if _cuda_cached is None:
        try:
            import ctranslate2
            _cuda_cached = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            _cuda_cached = False
    return _cuda_cached


def _resolve_device() -> tuple[str, str]:
    """(device, compute_type). DESK_WHISPER_DEVICE = auto|cpu|cuda (default 'auto':
    the GPU when present, else CPU). DESK_WHISPER_COMPUTE overrides compute type."""
    pref = os.environ.get("DESK_WHISPER_DEVICE", "auto").lower()
    compute = os.environ.get("DESK_WHISPER_COMPUTE")
    if pref == "cuda" or (pref == "auto" and _cuda_available()):
        return "cuda", compute or _GPU_COMPUTE
    return "cpu", compute or _CPU_COMPUTE


def planned_device() -> str:
    """The device the next transcription will TRY first — cheap, for the UI."""
    return _resolve_device()[0]


def active_device() -> str | None:
    """The device a model actually loaded on. None until the first transcription;
    reflects a GPU→CPU fallback if the GPU turned out to be unusable."""
    return _active_device


def device_label() -> str:
    """Short UI label: '<model> · GPU' or '<model> · CPU' (or an install hint)."""
    if not AVAILABLE:
        return "install desk[record]"
    dev = active_device() or planned_device()
    return f"{DEFAULT_MODEL} · {'GPU' if dev == 'cuda' else 'CPU'}"


def _load(model_size: str):
    global _active_device
    from faster_whisper import WhisperModel
    if model_size in _model_cache:
        return _model_cache[model_size]
    device, compute = _resolve_device()
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute)
    except Exception:
        if device == "cpu":
            raise                       # CPU is the floor; nothing to fall back to
        # GPU present but unusable (driver/cuDNN mismatch, OOM) -> fall back to CPU
        model = WhisperModel(model_size, device="cpu", compute_type=_CPU_COMPUTE)
        device = "cpu"
    _active_device = device
    _model_cache[model_size] = model
    return model


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


def transcribe_file(path: Path, model_size: str = DEFAULT_MODEL,
                    language: str | None = None) -> str:
    """Transcribe *any* audio file faster-whisper can decode (m4a, mp3, wav, …).

    Unlike transcribe(), which expects a 16 kHz mono WAV recorded by the Record
    panel, this hands the path straight to faster-whisper — its PyAV backend
    decodes and resamples any common format, so no manual conversion is needed.
    Uses the same GPU-or-CPU model resolution. Raises RuntimeError without the
    optional extra."""
    if not AVAILABLE:
        raise RuntimeError("transcription needs the optional extra: pip install desk[record]")
    model = _load(model_size)
    segments, _info = model.transcribe(str(path), language=language, beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()


def main(argv=None) -> None:
    """CLI `desk-transcribe`: transcribe existing audio files locally/offline
    (GPU when present, else CPU), writing `<name>.md` beside each one."""
    import argparse
    from datetime import datetime

    ap = argparse.ArgumentParser(
        prog="desk-transcribe",
        description="Transcribe audio files locally with faster-whisper "
                    "(offline; GPU when available, else CPU).")
    ap.add_argument("files", nargs="+", type=Path, help="audio files (m4a, mp3, wav, …)")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL,
                    help=f"whisper model name or local path (default: {DEFAULT_MODEL})")
    ap.add_argument("-l", "--language", default=None,
                    help="language code, e.g. es / en (default: auto-detect)")
    args = ap.parse_args(argv)

    if not AVAILABLE:
        raise SystemExit("transcription needs the optional extra: pip install desk[record]")

    for f in args.files:
        if not f.exists():
            print(f"skip (not found): {f}")
            continue
        text = transcribe_file(f, model_size=args.model, language=args.language)
        dev = active_device() or planned_device()
        backend = "GPU (float16)" if dev == "cuda" else "CPU (int8)"
        body = text if text.strip() else "_(no speech detected)_"
        out = f.with_suffix(".md")
        out.write_text(
            f"# Transcript — {f.name}\n\n"
            f"- Generated: {datetime.now():%Y-%m-%d %H:%M}\n"
            f"- Model: faster-whisper `{args.model}` on {backend}\n\n"
            f"{body}\n", encoding="utf-8")
        print(f"-> {out}  [{backend}]")


if __name__ == "__main__":
    main()
