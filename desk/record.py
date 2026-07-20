"""Meeting recorder — captures the machine's DEFAULT speaker (loopback) + DEFAULT
mic, mixed to 16 kHz mono, streamed to a WAV on disk. Portable: default devices,
no accounts, output under ~/.desk/transcripts/. Optional deps (soundcard, numpy)
are guarded so the panel degrades gracefully when they're absent.
"""
from __future__ import annotations

import threading
import wave
from datetime import datetime
from pathlib import Path

try:
    import numpy as np
    import soundcard as sc
    AVAILABLE = True
except Exception:                       # pragma: no cover - env without the extra
    AVAILABLE = False

TRANSCRIPTS_DIR = Path.home() / ".desk" / "transcripts"
SR = 16000          # whisper wants 16 kHz mono
CHUNK = 0.25        # seconds per capture chunk


def stamp(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d-%H%M%S")


class Recorder:
    """start()/stop() a background capture of loopback+mic into one 16k mono WAV.

    Each source streams to its own temp WAV in a daemon thread (low RAM); stop()
    mixes them into audio.wav. `level` is the latest RMS for a live meter."""

    def __init__(self, base_dir: Path | None = None):
        self.base = base_dir or TRANSCRIPTS_DIR
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.dir: Path | None = None
        self.level = 0.0
        self.frames = 0

    @property
    def running(self) -> bool:
        return bool(self._threads) and any(t.is_alive() for t in self._threads)

    @property
    def seconds(self) -> float:
        return self.frames / SR

    def start(self) -> Path:
        if not AVAILABLE:
            raise RuntimeError("recording needs the optional extra: pip install desk[record]")
        if self.running:
            return self.dir
        self.dir = self.base / stamp()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self._threads = []
        self.frames = 0
        self.level = 0.0
        spk = sc.default_speaker()
        loop = sc.get_microphone(spk.name, include_loopback=True)
        mic = sc.default_microphone()
        self._threads = [
            threading.Thread(target=self._capture, args=(loop, self.dir / "loopback.wav", True), daemon=True),
            threading.Thread(target=self._capture, args=(mic, self.dir / "mic.wav", False), daemon=True),
        ]
        for t in self._threads:
            t.start()
        return self.dir

    def _capture(self, device, path: Path, is_loop: bool) -> None:
        n = int(SR * CHUNK)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            try:
                with device.recorder(samplerate=SR, channels=1) as rec:
                    while not self._stop.is_set():
                        mono = rec.record(numframes=n).reshape(-1)
                        if is_loop:
                            self.frames += len(mono)
                            self.level = float(np.sqrt((mono ** 2).mean())) if len(mono) else 0.0
                        w.writeframes((np.clip(mono, -1, 1) * 32767).astype("<i2").tobytes())
            except Exception:               # a device that vanishes mid-record just ends its stream
                pass

    def stop(self) -> Path | None:
        if not self._threads:
            return None
        self._stop.set()
        for t in self._threads:
            t.join(timeout=4)
        out = self.dir / "audio.wav"
        _mix(self.dir / "loopback.wav", self.dir / "mic.wav", out)
        self._threads = []
        return out if out.exists() else None


def _read_i32(path: Path):
    if not path.exists():
        return np.zeros(0, dtype=np.int32)
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.int32)


def _mix(a: Path, b: Path, out: Path) -> None:
    xa, xb = _read_i32(a), _read_i32(b)
    n = max(len(xa), len(xb))
    if n == 0:
        return
    buf = np.zeros(n, dtype=np.int32)
    buf[:len(xa)] += xa
    buf[:len(xb)] += xb
    clipped = np.clip(buf, -32768, 32767).astype("<i2")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(clipped.tobytes())
    for p in (a, b):
        try:
            p.unlink()
        except OSError:
            pass
