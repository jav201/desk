"""Pull the audio track off a web video (YouTube and ~1800 other sites) so it can
be transcribed locally — for studying tutorials, talks and interviews.

This is the ONLY part of desk that touches the network, so it is an opt-in extra
(`pip install desk[web]`) and everything else keeps working offline. Safety rails
that matter, since the input is an arbitrary URL:

  * yt-dlp is driven through its PYTHON API — the URL is never interpolated into
    a shell command;
  * `noplaylist` is forced, so pasting a playlist/channel link grabs ONE video
    instead of silently pulling hundreds;
  * the output path is a fixed, sanitised directory under ~/.desk/transcripts/;
  * the duration is checked BEFORE downloading and refused past a cap, so a
    12-hour livestream can't quietly fill the disk or hog the GPU.

No re-encoding: we keep the site's native audio stream (m4a/webm/opus), which
faster-whisper decodes directly via PyAV — so ffmpeg is NOT required.

Respect each site's terms of service and the rights of content owners; use this
on material you are allowed to process.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

TRANSCRIPTS_DIR = Path.home() / ".desk" / "transcripts"
MAX_SECONDS = 2 * 60 * 60          # refuse past 2 h unless the caller raises it
AVAILABLE = importlib.util.find_spec("yt_dlp") is not None

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def is_url(text: str) -> bool:
    """True for an http(s) URL — what the picker uses to tell a URL from a path."""
    return bool(_URL_RE.match(text.strip()))


def _require_web_url(url: str) -> str:
    """Accept ONLY http/https. yt-dlp happily resolves `file://` (and other local
    schemes), which would turn "paste a link" into "read an arbitrary path off my
    disk". Every network entry point goes through this."""
    url = (url or "").strip()
    if not is_url(url):
        raise RuntimeError("only http(s) links are supported")
    return url


def safe_name(title: str, limit: int = 60) -> str:
    """A title turned into a filesystem-safe folder name (Windows-hostile chars
    removed, trailing dots/spaces stripped, length capped). Never empty."""
    name = _BAD_CHARS.sub("", title or "").strip().strip(".")
    name = re.sub(r"\s+", " ", name)[:limit].strip()
    return name or "video"


def probe(url: str) -> dict:
    """Metadata only — no download. Returns {title, duration, extractor, webpage_url}.
    Raises RuntimeError without the extra, or on an unresolvable URL."""
    if not AVAILABLE:
        raise RuntimeError("web audio needs the optional extra: pip install desk[web]")
    url = _require_web_url(url)
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=False)
    except Exception as exc:                       # network, geo-block, removed…
        raise RuntimeError(f"couldn't read that URL: {exc}") from exc
    if info.get("_type") == "playlist":            # belt: take the first entry
        entries = [e for e in (info.get("entries") or []) if e]
        info = entries[0] if entries else info
    return {"title": info.get("title") or "video",
            "duration": info.get("duration"),
            "extractor": info.get("extractor"),
            "webpage_url": info.get("webpage_url") or url}


def fetch_audio(url: str, base_dir: Path | None = None, stamp: str | None = None,
                max_seconds: int = MAX_SECONDS, progress=None) -> tuple[Path, dict]:
    """Download the best AUDIO-ONLY stream for `url` into its own folder under
    `base_dir`, keeping the native container (no ffmpeg re-encode).

    Returns (audio_path, meta). `progress` is an optional callback taking
    (fraction 0..1 or None, human status str). Raises RuntimeError if the extra
    is missing, the URL can't be read, it is longer than `max_seconds`, or the
    download produced nothing."""
    if not AVAILABLE:
        raise RuntimeError("web audio needs the optional extra: pip install desk[web]")
    url = _require_web_url(url)
    import yt_dlp

    if progress:
        progress(None, "reading…")
    meta = probe(url)
    dur = meta.get("duration")
    if dur and max_seconds and dur > max_seconds:
        raise RuntimeError(
            f"that video is {dur // 3600}h{dur % 3600 // 60:02d}m — over the "
            f"{max_seconds // 3600}h limit")

    from . import record                            # reuse the same timestamp form
    base = base_dir or TRANSCRIPTS_DIR
    out_dir = base / f"{stamp or record.stamp()}-{safe_name(meta['title'])}"
    out_dir.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if not progress:
            return
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            got = d.get("downloaded_bytes") or 0
            progress(got / total if total else None, "downloading…")
        elif d.get("status") == "finished":
            progress(1.0, "downloaded")

    opts = {
        "quiet": True, "no_warnings": True,
        # `quiet` does NOT silence the progress bar: yt-dlp would write
        # "[download] 27.0%…" straight to stdout and corrupt the Textual screen.
        # We surface progress through `progress_hooks` instead.
        "noprogress": True,
        "noplaylist": True,                        # one video, never a playlist
        "format": "bestaudio/best",                # audio-only when offered
        "outtmpl": str(out_dir / "audio.%(ext)s"),  # fixed, sanitised destination
        "progress_hooks": [hook],
        "retries": 3,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.extract_info(url, download=True)
    except Exception as exc:
        raise RuntimeError(f"download failed: {exc}") from exc

    got = sorted(p for p in out_dir.glob("audio.*") if p.is_file())
    if not got:
        raise RuntimeError("download produced no audio file")
    return got[0], meta
