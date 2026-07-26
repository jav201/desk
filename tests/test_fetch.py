"""Web-video audio fetch: URL detection, the security guards (scheme allow-list,
no-playlist, duration cap, name sanitising), and the CLI's URL branch.

yt_dlp is faked throughout — NO test performs a real download. The guards are
the point of this file: an arbitrary URL is handed to a downloader running on
the user's machine, so each mitigation in the spec has a test that fails if it
is removed.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from desk import fetch
from desk import transcribe as T


# ---- fake yt_dlp ------------------------------------------------------------
def install_fake_ytdlp(monkeypatch, *, info=None, on_download=None, raises=None):
    """Install a fake yt_dlp module; returns a dict recording the opts it saw."""
    seen = {}

    class FakeYDL:
        def __init__(self, opts):
            seen["opts"] = opts
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def extract_info(self, url, download=False):
            seen.setdefault("calls", []).append((url, download))
            if raises:
                raise raises
            if download and on_download:
                on_download(seen["opts"])
            return info or {}

    mod = types.ModuleType("yt_dlp")
    mod.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", mod)
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    return seen


INFO = {"title": "Deep Learning Talk", "duration": 600,
        "extractor": "youtube", "webpage_url": "https://youtu.be/abc"}


# ---- pure helpers -----------------------------------------------------------
def test_is_url_distinguishes_urls_from_paths():
    assert fetch.is_url("https://youtu.be/abc") and fetch.is_url("http://x.dev/v")
    assert not fetch.is_url(r"C:\Users\me\clip.m4a")
    assert not fetch.is_url("/home/me/clip.mp3")
    assert not fetch.is_url("")


def test_only_http_schemes_are_accepted(monkeypatch):
    """AC-4 (the security finding): yt-dlp resolves file:// happily, which would
    turn "paste a link" into "read an arbitrary path off my disk". Every network
    entry point must refuse non-http(s) BEFORE yt-dlp sees it."""
    install_fake_ytdlp(monkeypatch, info=INFO)
    for bad in ("file:///C:/Windows/System32/config/SAM", "ftp://host/f.mp3",
                "file://etc/passwd", r"C:\secret.wav", "javascript:alert(1)"):
        with pytest.raises(RuntimeError, match="only http"):
            fetch.probe(bad)
        with pytest.raises(RuntimeError, match="only http"):
            fetch.fetch_audio(bad)


def test_safe_name_strips_filesystem_hostile_characters():
    """AC-5: the remote title becomes a folder name — it must not be able to
    escape or break the path."""
    got = fetch.safe_name('a/b\\c:d*e?f"g<h>i|j')
    assert not any(ch in got for ch in '/\\:*?"<>|')
    assert fetch.safe_name("") == "video"                 # never empty
    assert fetch.safe_name("...") == "video"
    assert len(fetch.safe_name("x" * 200)) <= 60          # capped
    assert ".." not in fetch.safe_name("../../etc/passwd")


# ---- probe / fetch guards ---------------------------------------------------
def test_probe_returns_metadata_without_downloading(monkeypatch):
    seen = install_fake_ytdlp(monkeypatch, info=INFO)
    meta = fetch.probe("https://youtu.be/abc")
    assert meta["title"] == "Deep Learning Talk" and meta["duration"] == 600
    assert seen["calls"] == [("https://youtu.be/abc", False)]      # download=False
    assert seen["opts"]["skip_download"] is True


def test_playlist_url_takes_one_video_only(monkeypatch):
    """AC-2: pasting a playlist/channel link must grab ONE video, never hundreds."""
    seen = install_fake_ytdlp(monkeypatch, info=INFO)
    fetch.probe("https://youtube.com/playlist?list=PL123")
    assert seen["opts"]["noplaylist"] is True


def test_duration_cap_refuses_before_downloading(monkeypatch, tmp_path):
    """AC-3: a 4-hour livestream must be refused BEFORE any bytes are fetched —
    the check is worthless if it runs after the download."""
    long_info = dict(INFO, duration=4 * 3600)
    seen = install_fake_ytdlp(monkeypatch, info=long_info)
    with pytest.raises(RuntimeError, match="over the"):
        fetch.fetch_audio("https://youtu.be/abc", base_dir=tmp_path)
    assert all(download is False for _, download in seen["calls"])   # never downloaded
    assert list(tmp_path.iterdir()) == []                            # nothing written


def test_fetch_downloads_audio_into_a_sanitised_folder(monkeypatch, tmp_path):
    """AC-1: one audio file lands in its own folder named from the stamp+title."""
    def on_download(opts):                       # simulate yt-dlp writing the file
        out = Path(opts["outtmpl"].replace("%(ext)s", "m4a"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-audio")

    seen = install_fake_ytdlp(monkeypatch, info=INFO, on_download=on_download)
    path, meta = fetch.fetch_audio("https://youtu.be/abc", base_dir=tmp_path,
                                   stamp="2026-07-24-120000")
    assert path.exists() and path.name == "audio.m4a"
    assert path.parent.name == "2026-07-24-120000-Deep Learning Talk"
    assert path.parent.parent == tmp_path        # never escapes the given base
    assert meta["title"] == "Deep Learning Talk"
    assert seen["opts"]["format"].startswith("bestaudio")   # audio only, no video
    assert seen["opts"]["noplaylist"] is True
    # caught by the real smoke: `quiet` does NOT silence yt-dlp's progress bar,
    # and "[download] 27.0%" written to stdout corrupts the Textual screen.
    assert seen["opts"]["noprogress"] is True


def test_fetch_reports_progress(monkeypatch, tmp_path):
    """AC-8's data source: the panel can only show progress if the hook fires."""
    calls = []

    def on_download(opts):
        hook = opts["progress_hooks"][0]
        hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 200})
        hook({"status": "finished"})
        out = Path(opts["outtmpl"].replace("%(ext)s", "webm"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x")

    install_fake_ytdlp(monkeypatch, info=INFO, on_download=on_download)
    fetch.fetch_audio("https://youtu.be/abc", base_dir=tmp_path,
                      progress=lambda frac, status: calls.append((frac, status)))
    fracs = [f for f, _ in calls]
    assert 0.25 in fracs                                  # 50 of 200 bytes
    # the status carries human size, which is what the panel shows
    assert any(s.startswith("downloading…") and "MB" in s for _, s in calls)
    assert calls[-1] == (1.0, "downloaded")


def test_fetch_requires_the_web_extra(monkeypatch, tmp_path):
    """AC-9: without [web] installed, the URL paths say so and do nothing else."""
    monkeypatch.setattr(fetch, "AVAILABLE", False)
    with pytest.raises(RuntimeError, match=r"desk\[web\]"):
        fetch.fetch_audio("https://youtu.be/abc", base_dir=tmp_path)
    with pytest.raises(RuntimeError, match=r"desk\[web\]"):
        fetch.probe("https://youtu.be/abc")


def test_unreadable_url_raises_a_clean_error(monkeypatch):
    install_fake_ytdlp(monkeypatch, raises=Exception("Video unavailable"))
    with pytest.raises(RuntimeError, match="couldn't read that URL"):
        fetch.probe("https://youtu.be/gone")


# ---- CLI --------------------------------------------------------------------
def test_cli_transcribes_a_url_and_records_the_source(tmp_path, monkeypatch, capsys):
    """AC-6: `desk-transcribe <url>` fetches then transcribes, and the .md names
    the source URL and title (so a transcript is traceable to its video)."""
    audio = tmp_path / "2026-07-24-Talk" / "audio.m4a"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"x")
    monkeypatch.setattr(T, "AVAILABLE", True)
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    monkeypatch.setattr(fetch, "fetch_audio", lambda url, **k: (audio, INFO))
    monkeypatch.setattr(T, "transcribe_file", lambda p, **k: "what the speaker said")

    T.main(["https://youtu.be/abc"])

    md = (audio.parent / "audio.md").read_text(encoding="utf-8")
    assert "# Transcript — Deep Learning Talk" in md
    assert "- Source: https://youtu.be/abc" in md
    assert "what the speaker said" in md


def test_cli_file_path_still_works_and_has_no_source_line(tmp_path, monkeypatch):
    """AC-6 (other half): the file behaviour is untouched by the URL branch."""
    f = tmp_path / "memo.mp3"
    f.write_bytes(b"x")
    monkeypatch.setattr(T, "AVAILABLE", True)
    monkeypatch.setattr(T, "transcribe_file", lambda p, **k: "local words")

    T.main([str(f)])

    md = (tmp_path / "memo.md").read_text(encoding="utf-8")
    assert "# Transcript — memo.mp3" in md and "local words" in md
    assert "- Source:" not in md


def test_cli_url_without_web_extra_skips_with_a_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(T, "AVAILABLE", True)
    monkeypatch.setattr(fetch, "AVAILABLE", False)
    T.main(["https://youtu.be/abc"])
    assert "desk[web]" in capsys.readouterr().out
