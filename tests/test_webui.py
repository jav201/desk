"""In-app web-video transcription: the `u` prompt, the `i` picker's URL branch,
the fetching panel state and its 10 Hz repaint lane.

Nothing here downloads: `fetch.fetch_audio` is monkeypatched everywhere.
"""
from __future__ import annotations

import re

from desk import fetch, record
from desk.app import Deck
from desk.picker import AudioPicker, UrlPrompt

URL = "https://youtu.be/abc123"


def _plain(markup: str) -> str:
    return re.sub(r"\[/?[^\]]*\]", "", markup)


def _body(app) -> str:
    return _plain(str(app.query_one("#stage-body").render()))


# ---- the fetching panel state (AC-8) ----------------------------------------
def test_probe_phase_says_nothing_is_downloading_yet():
    """While only metadata is being read, the panel must NOT imply a download is
    under way — that distinction is the honest part of the state."""
    out = _plain(record.render_fetching({"url": URL, "site": "youtube"}, phase=0))
    assert "no download yet" in out
    assert "%" not in out                                  # no progress bar yet
    assert any(ch in out for ch in record.FETCH_SPIN)      # the spinner is drawn


def test_download_phase_shows_bar_percent_title_and_size():
    info = {"url": URL, "site": "youtube", "title": "Deep Learning Talk",
            "duration": 2462, "frac": 0.5, "status": "downloading…  9.2 / 18.4 MB"}
    out = _plain(record.render_fetching(info))
    assert "Deep Learning Talk" in out
    assert "41:02" in out                                   # duration, mm:ss
    assert "50%" in out
    assert "9.2 / 18.4 MB" in out
    assert "▊" in out and "░" in out                        # the meter-lane bar


def test_fetch_bar_tracks_the_fraction_at_constant_width():
    strip = lambda f: _plain(record._fetch_bar(f))
    counts = [strip(f).count("▊") for f in (0.0, 0.25, 0.5, 1.0)]
    assert counts == sorted(counts) and counts[0] == 0
    assert counts[-1] == record.METER_WIDTH                 # full at 100%
    for f in (0.0, 0.4, 1.0):                               # width never moves
        assert len(strip(f)) == record.METER_WIDTH


def test_fetching_state_routes_through_render_body():
    out = _plain(record.render_body("fetching", fetch={"url": URL, "site": "x"}))
    assert "fetching audio" in out


def test_idle_panel_offers_the_u_key():
    assert "transcribe a web video" in _plain(record.render_body("idle"))


def test_record_hint_bar_includes_url():
    from desk import hints
    assert "url" in _plain(hints.render("record", 80))


# ---- the `u` prompt (AC-7, AC-4 in the UI) ----------------------------------
async def test_u_opens_the_url_prompt_and_escape_cancels(monkeypatch):
    from desk import transcribe
    monkeypatch.setattr(transcribe, "AVAILABLE", True)
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    app = Deck()
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.action_expand("record")
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        assert isinstance(app.screen, UrlPrompt)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, UrlPrompt)


async def test_url_prompt_refuses_non_http_and_stays_open(monkeypatch):
    """The scheme rule is enforced in the UI too, so a file:// never even starts
    a job — and the user is told why instead of the modal silently doing nothing."""
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    app = Deck()
    dismissed = []
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.push_screen(UrlPrompt(), lambda r: dismissed.append(r))
        await pilot.pause()
        prompt = app.screen
        prompt.query_one("#url-input").value = "file:///C:/Windows/win.ini"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, UrlPrompt)            # still open
        assert not dismissed                                 # nothing handed back
        assert "only http(s)" in _plain(str(prompt.query_one("#url-note").render()))


async def test_url_prompt_dismisses_with_a_valid_url(monkeypatch):
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    app = Deck()
    got = {}
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.push_screen(UrlPrompt(), lambda r: got.update(res=r))
        await pilot.pause()
        app.screen.query_one("#url-input").value = URL
        await pilot.press("enter")
        await pilot.pause()
        assert got["res"] == URL


async def test_u_reports_when_the_web_extra_is_missing(monkeypatch):
    """AC-9: no [web] -> a clear message, and no modal opens."""
    from desk import transcribe
    monkeypatch.setattr(transcribe, "AVAILABLE", True)
    monkeypatch.setattr(fetch, "AVAILABLE", False)
    app = Deck()
    notes = []
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.notify = lambda *a, **k: notes.append(a[0] if a else "")
        app.action_transcribe_url()
        await pilot.pause()
        assert not isinstance(app.screen, UrlPrompt)
        assert any("desk[web]" in n for n in notes)


# ---- the `i` picker's URL branch (AC-7) -------------------------------------
async def test_picker_swaps_the_browser_for_a_link_card_on_a_url(monkeypatch, tmp_path):
    """Typing a URL into the file picker must visibly switch modes — the folder
    browser is meaningless for a URL."""
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    (tmp_path / "a.mp3").write_bytes(b"x")
    app = Deck()
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause()
        app.push_screen(AudioPicker(start=tmp_path))
        await pilot.pause()
        pk = app.screen
        assert "a.mp3" in _plain(str(pk.query_one("#pick-body").render()))
        pk.query_one("#pick-path").value = URL              # fires on_input_changed
        await pilot.pause()
        card = _plain(str(pk.query_one("#pick-body").render()))
        assert "transcribe a web video" in card and "a.mp3" not in card


async def test_picker_hands_back_a_url_string(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    app = Deck()
    got = {}
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause()
        app.push_screen(AudioPicker(start=tmp_path), lambda r: got.update(res=r))
        await pilot.pause()
        app.screen.query_one("#pick-path").value = URL
        await pilot.press("enter")
        await pilot.pause()
        assert got["res"] == URL                            # a str, not a Path


# ---- the job wiring (AC-7, AC-8) --------------------------------------------
async def test_url_job_enters_fetching_and_the_fast_lane_repaints(monkeypatch):
    """The panel must show live download progress: entering the job sets the
    fetching state, and the 10 Hz lane repaints it as `_fetch_info` changes."""
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    app = Deck()
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        monkeypatch.setattr(app, "run_worker", lambda *a, **k: None)   # don't fetch
        app._start_url_job(URL)
        await pilot.pause()
        assert app._rec_state == "fetching" and app.mode == "record"
        app._fetch_info.update(frac=0.5, title="A Talk", duration=120,
                               status="downloading…  1.0 / 2.0 MB")
        app._meter_tick()
        await pilot.pause()
        body = _body(app)
        assert "50%" in body and "A Talk" in body


async def test_picked_url_starts_a_fetch_job(monkeypatch):
    """A URL from EITHER entry point lands in the same job."""
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    app = Deck()
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        monkeypatch.setattr(app, "run_worker", lambda *a, **k: None)
        app._on_file_picked(URL)                            # picker gave a str
        await pilot.pause()
        assert app._rec_state == "fetching"
        assert app._fetch_info["url"] == URL


async def test_failed_fetch_returns_to_idle_and_reports(monkeypatch):
    """AC-8: a refused/failed fetch must not strand the panel in 'fetching'."""
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    def boom(url, **k):
        raise RuntimeError("that video is 3h07m — over the 2h limit")
    monkeypatch.setattr(fetch, "fetch_audio", boom)
    app = Deck()
    notes = []
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.notify = lambda *a, **k: notes.append(a[0] if a else "")
        monkeypatch.setattr(app, "call_from_thread", lambda fn, *a, **k: fn(*a, **k))
        app._run_url_job(URL)                               # the worker body
        await pilot.pause()
        assert app._rec_state == "idle"
        assert app._fetch_info == {}
        assert any("over the 2h limit" in n for n in notes)
