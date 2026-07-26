"""Meeting recorder — captures the machine's DEFAULT speaker (loopback) + DEFAULT
mic, mixed to 16 kHz mono, streamed to a WAV on disk. Portable: default devices,
no accounts, output under ~/.desk/transcripts/. Optional deps (soundcard, numpy)
are guarded so the panel degrades gracefully when they're absent.
"""
from __future__ import annotations

import importlib.util
import math
import threading
import wave
import json
from datetime import datetime
from pathlib import Path

# Presence check only — do NOT import numpy/soundcard here. Importing soundcard
# initializes the Windows WASAPI/COM audio stack, which sits in desk's startup
# path and can stall the first paint by seconds on some machines. The heavy
# imports are deferred to the functions that record/mix (mirrors transcribe.py).
AVAILABLE = all(importlib.util.find_spec(m) for m in ("numpy", "soundcard"))

TRANSCRIPTS_DIR = Path.home() / ".desk" / "transcripts"
SR = 16000          # whisper wants 16 kHz mono
CHUNK = 0.25        # seconds per capture chunk
RECORD_SETTINGS_PATH = Path.home() / ".desk" / "record.json"
AUTO_MIN_DEFAULT = 60
AUTO_MIN_LO = 5
AUTO_MIN_HI = 240
AUTO_STEP = 5


def clamp_minutes(minutes: int) -> int:
    return max(AUTO_MIN_LO, min(AUTO_MIN_HI, minutes))


def load_settings(path: Path | None = None) -> dict:
    """Auto-stop prefs {enabled: bool, minutes: int}. Missing/corrupt -> defaults
    (60 min, ON). minutes is clamped. Never raises."""
    path = path or RECORD_SETTINGS_PATH
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    try:
        minutes = int(d.get("minutes", AUTO_MIN_DEFAULT))
    except Exception:
        minutes = AUTO_MIN_DEFAULT
    return {"enabled": bool(d.get("enabled", True)), "minutes": clamp_minutes(minutes)}


def save_settings(enabled: bool, minutes: int, path: Path | None = None) -> None:
    path = path or RECORD_SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabled": bool(enabled), "minutes": int(minutes)}),
                    encoding="utf-8")


def should_autostop(seconds: float, auto_on: bool, minutes: int) -> bool:
    return bool(auto_on) and seconds >= minutes * 60


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
        # per-stream RMS, updated by each capture thread; the meter shows the
        # louder of the two so the user's OWN mic moves it, not just loopback.
        self._level_loop = 0.0
        self._level_mic = 0.0
        self.frames = 0

    @property
    def level(self) -> float:
        return max(self._level_loop, self._level_mic)

    @property
    def running(self) -> bool:
        return bool(self._threads) and any(t.is_alive() for t in self._threads)

    @property
    def seconds(self) -> float:
        return self.frames / SR

    def start(self) -> Path:
        if not AVAILABLE:
            raise RuntimeError("recording needs the optional extra: pip install desk[record]")
        import soundcard as sc            # deferred: keeps WASAPI init off startup
        if self.running:
            return self.dir
        self.dir = self.base / stamp()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self._threads = []
        self.frames = 0
        self._level_loop = 0.0
        self._level_mic = 0.0
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
        import numpy as np
        n = int(SR * CHUNK)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            try:
                with device.recorder(samplerate=SR, channels=1) as rec:
                    while not self._stop.is_set():
                        mono = rec.record(numframes=n).reshape(-1)
                        lvl = float(np.sqrt((mono ** 2).mean())) if len(mono) else 0.0
                        if is_loop:
                            self.frames += len(mono)
                            self._level_loop = lvl
                        else:
                            self._level_mic = lvl
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
    import numpy as np
    if not path.exists():
        return np.zeros(0, dtype=np.int32)
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.int32)


def _mix(a: Path, b: Path, out: Path) -> None:
    import numpy as np
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


# ---- panel rendering (Textual markup) --------------------------------------
def _mmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


METER_WIDTH = 28          # cells in the VU bar
METER_FLOOR_DB = -48.0    # RMS quieter than this reads as empty


def _meter(level: float, width: int = METER_WIDTH) -> str:
    """A live VU bar on a DECIBEL (perceptual) scale — a linear RMS scale left
    normal speech (RMS ~0.03–0.1) barely filling. Maps [floor dB .. 0 dB] onto
    the bar and colours it green→gold→red so a glance reads quiet/talking/clipping."""
    db = 20.0 * math.log10(level) if level > 1e-6 else -120.0
    frac = (db - METER_FLOOR_DB) / (0.0 - METER_FLOOR_DB)
    filled = max(0, min(width, round(frac * width)))
    lo_w, mid_w = int(width * 0.6), int(width * 0.25)
    lo = min(filled, lo_w)
    mid = min(max(0, filled - lo), mid_w)
    hi = max(0, filled - lo - mid)
    return (f"[#3fb950]{'▊' * lo}[/][#ffd166]{'▊' * mid}[/][#ff3b30]{'▊' * hi}[/]"
            f"[dim]{'░' * (width - filled)}[/dim]")


FETCH_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"      # braille spinner for the metadata-probe phase
_FETCH_FILL = "#2dd4bf"           # teal: the download lane
_FETCH_LEAD = "#7ff3e4"           # brighter leading cell, so the bar ARRIVES


def _fetch_bar(frac: float, width: int = METER_WIDTH) -> str:
    """Download progress drawn on the VU meter's exact geometry — the same 28
    cells the eye already reads in this panel, so the bar needs no learning."""
    filled = max(0, min(width, round((frac or 0.0) * width)))
    out = ""
    if filled > 1:
        out += f"[{_FETCH_FILL}]{'▊' * (filled - 1)}[/]"
    if filled >= 1:
        out += f"[{_FETCH_LEAD}]▊[/]"
    return out + f"[dim]{'░' * (width - filled)}[/dim]"


def render_fetching(info: dict, phase: int = 0) -> str:
    """The 'pulling a web video's audio' state. `info` carries what is known so
    far: url, site, title, duration, frac (None while only probing) and status.
    `phase` advances the spinner on the fast repaint lane."""
    out = ["[bold #2dd4bf]RECORD[/]", ""]
    site = info.get("site") or "web"
    out.append(f"[#2dd4bf]◆[/] fetching audio   [dim]{site}[/dim]")
    frac = info.get("frac")
    if frac is None:                       # probing: metadata only, nothing pulled
        spin = FETCH_SPIN[phase % len(FETCH_SPIN)]
        out.append(f"[#2dd4bf]{spin}[/] [#ffd166]reading title & duration — "
                   f"no download yet[/]")
        out.append(f"[dim]{(info.get('url') or '')[:52]}[/dim]")
    else:
        if info.get("title"):
            out.append(f"[#dbe4ee]{info['title'][:52]}[/]")
        dur = _mmss(info["duration"]) if info.get("duration") else "?"
        out.append(f"[dim]{dur} · audio only · no re-encode[/dim]")
        out.append("")
        out.append(f"  {_fetch_bar(frac)}  [#ffd166]{round(frac * 100):3d}%[/]")
        out.append(f"  [dim]{info.get('status') or 'downloading…'}[/dim]")
    out.append("")
    # NOT "esc cancels": esc collapses the panel, the worker keeps going. Say so.
    out.append("[dim]esc hides this · the job keeps running[/dim]")
    out += ["", "[#ff8c42]▲[/] [dim]respect each site's terms and the rights of "
            "content owners[/dim]"]
    return "\n".join(out)


def _web_suffix() -> str:
    """Say so inline when the network extra isn't installed, instead of letting
    the key look broken when pressed."""
    try:
        from . import fetch
        return "" if fetch.AVAILABLE else "  [dim](needs desk\\[web])[/dim]"
    except Exception:
        return ""


def _whisper_label() -> str:
    """Colour-coded device chip for the panel: green GPU / gold CPU, plus the
    model name. Reflects the actual device once a transcription has run."""
    try:
        from . import transcribe
        dev = transcribe.active_device() or transcribe.planned_device()
        model = transcribe.DEFAULT_MODEL
    except Exception:
        return "[dim]local[/dim]"
    if dev == "cuda":
        return f"[#3fb950]GPU[/] [dim]· {model}[/dim]"
    return f"[#ffd166]CPU[/] [dim]· {model}[/dim]"


def render_tile(state: str, seconds: float = 0.0, level: float = 0.0) -> str:
    if not AVAILABLE:
        return "[dim]● record  (pip install desk\\[record])[/dim]"
    if state == "recording":
        return f"[#ff3b30]● REC {_mmss(seconds)}[/]"
    if state == "transcribing":
        return "[#ffd166]◌ transcribing…[/]"
    return "[dim]● record a meeting[/dim]"


def render_body(state: str, seconds: float = 0.0, level: float = 0.0,
                last: str | None = None, auto_on: bool = True,
                auto_min: int = AUTO_MIN_DEFAULT, fetch: dict | None = None,
                phase: int = 0) -> str:
    if state == "fetching":
        return render_fetching(fetch or {}, phase)
    out = ["[bold #2dd4bf]RECORD[/]", ""]
    if not AVAILABLE:
        out += ["[dim]meeting recorder + local transcription[/dim]", "",
                "[#ff8c42]not enabled[/] — install the optional extra:",
                "[dim]  pip install desk\\[record][/dim]"]
        return "\n".join(out)
    if state == "recording":
        if auto_on:
            remaining = max(0, auto_min * 60 - int(seconds))
            auto_line = f"[#ffd166]auto-stop in {_mmss(remaining)}[/] [#3fb950]\\[on][/]"
        else:
            auto_line = "[dim]auto-stop: off[/dim]"
        out += [f"[#ff3b30]● recording[/]   {_mmss(seconds)}",
                auto_line, "",
                "  " + _meter(level), "",
                "[dim]space stops · a auto-stop · +/- adjust[/dim]"]
    elif state == "transcribing":
        out += [f"[#ffd166]◌ transcribing…[/]   [dim](local whisper on[/dim] "
                f"{_whisper_label()} [dim]— a moment)[/dim]"]
    else:
        out += ["[dim]captures system audio + your mic, transcribes locally[/dim]", "",
                "[#ffd166]space[/] start recording",
                "[#ffd166]i[/] transcribe an existing file",
                "[#ffd166]u[/] transcribe a web video" + _web_suffix(),
                "[#ffd166]t[/] open transcripts folder"]
        if auto_on:
            out.append(f"[#ffd166]auto-stop[/] {auto_min} min   [#ffd166]a[/] on/off · "
                       f"[#ffd166]+/-[/] ±5 min")
        else:
            out.append("[#ffd166]auto-stop[/] off   [#ffd166]a[/] on/off")
        out.append(f"[dim]whisper:[/dim] {_whisper_label()}")
        if last:
            preview = last[:220] + ("…" if len(last) > 220 else "")
            out += ["", "[dim]last transcript:[/dim]", preview]
    out += ["", "[#ff8c42]▲[/] [dim]recording may require participants' consent[/dim]"]
    return "\n".join(out)
