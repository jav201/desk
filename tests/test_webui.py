"""In-app web-video transcription: the `u` prompt, the `i` picker's URL branch,
the fetching panel state and its 10 Hz repaint lane.

Nothing here downloads: `fetch.fetch_audio` is monkeypatched everywhere.
"""
from __future__ import annotations

import re

from textual.content import Content

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


def test_download_phase_shows_field_percent_title_and_size():
    info = {"url": URL, "site": "youtube", "title": "Deep Learning Talk",
            "duration": 2462, "frac": 0.5, "status": "downloading…  9.2 / 18.4 MB"}
    out = _plain(record.render_fetching(info))
    assert "Deep Learning Talk" in out
    assert "41:02" in out                                   # duration, mm:ss
    assert "50%" in out
    assert "9.2 / 18.4 MB" in out
    assert any(0x2800 <= ord(ch) <= 0x28ff for ch in out)   # the braille intake


def _lit(frac, phase=0):
    total = 0
    for ln in record._intake_field(frac, phase):
        for ch in _plain(ln):
            if ch != " ":
                total += bin(ord(ch) - 0x2800).count("1")
    return total


def test_intake_field_fills_with_progress():
    """Treatment C: the field is the progress. If its mass stopped tracking the
    fraction the panel would be decoration, not a readout."""
    counts = [_lit(f / 20) for f in range(21)]
    assert counts == sorted(counts)                         # monotone, never regresses
    assert _lit(0.5) > _lit(0.15) > 0
    full = record.INTAKE_COLS * 2 * record.INTAKE_ROWS * 4
    assert _lit(1.0) == full        # 100% is genuinely FULL, no ragged edge left


def test_intake_field_is_width_exact_and_narrow_glyphs():
    import unicodedata
    rows = record._intake_field(0.5)
    assert len(rows) == record.INTAKE_ROWS
    assert len({len(_plain(r)) for r in rows}) == 1
    for r in rows:
        for ch in _plain(r):
            assert unicodedata.east_asian_width(ch) not in ("W", "F"), repr(ch)


def test_intake_shape_is_stable_across_repaints():
    """The jitter is seeded, so a repaint at the same fraction must not reshuffle
    the field — otherwise it would boil instead of fill."""
    assert record._intake_field(0.4, phase=2) == record._intake_field(0.4, phase=2)
    body = lambda p: _plain(record.render_fetching({"frac": 0.4, "site": "y"}, p))
    assert body(1) != body(2)        # …but the sparks ahead of the front do twinkle


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


async def test_clipboard_link_is_offered_but_never_auto_submitted(monkeypatch):
    """The copy → u → Enter flow: a link already on the clipboard is offered as
    the (dim) placeholder and accepted by Enter on an empty box. It must NOT
    submit on its own — the clipboard may hold something the user never meant
    to send anywhere."""
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    app = Deck()
    got = {}
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.push_screen(UrlPrompt(suggestion=URL), lambda r: got.update(res=r))
        await pilot.pause()
        prompt = app.screen
        assert prompt.query_one("#url-input").placeholder == URL   # offered, dim
        assert prompt.query_one("#url-input").value == ""          # box still empty
        assert "clipboard" in _plain(str(prompt.query_one("#url-note").render()))
        assert not got                                             # nothing sent yet
        await pilot.press("enter")                                 # the user accepts
        await pilot.pause()
        assert got["res"] == URL


async def test_typing_replaces_the_clipboard_suggestion(monkeypatch):
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    other = "https://vimeo.com/999"
    app = Deck()
    got = {}
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.push_screen(UrlPrompt(suggestion=URL), lambda r: got.update(res=r))
        await pilot.pause()
        app.screen.query_one("#url-input").value = other
        await pilot.press("enter")
        await pilot.pause()
        assert got["res"] == other                 # what was typed wins


async def test_no_clipboard_link_leaves_the_prompt_empty(monkeypatch):
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    app = Deck()
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.push_screen(UrlPrompt(suggestion=""))       # clipboard held no link
        await pilot.pause()
        prompt = app.screen
        assert prompt.query_one("#url-input").placeholder.startswith("https://…")
        await pilot.press("enter")                      # Enter on empty does nothing
        await pilot.pause()
        assert isinstance(app.screen, UrlPrompt)        # still open, not dismissed


def test_clipboard_url_only_returns_http_links(monkeypatch):
    """Whatever is on the clipboard, only an http(s) link is ever offered."""
    from desk import picker
    for junk in ("just some copied text", "C:\\Users\\me\\secret.txt",
                 "file:///etc/passwd", ""):
        monkeypatch.setattr(picker, "clipboard_text", lambda j=junk: j)
        assert picker.clipboard_url() is None
    monkeypatch.setattr(picker, "clipboard_text", lambda: f"  {URL}  \nsecond line")
    assert picker.clipboard_url() == URL                # trimmed, first line only


def test_clipboard_read_failure_is_survivable(monkeypatch):
    from desk import picker
    def boom():
        raise OSError("no clipboard here")
    monkeypatch.setattr(picker, "clipboard_text", boom)
    assert picker.clipboard_url() is None                # guarded, never raises


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
        # THE ORACLE IS WHAT THE READER SEES. This used to assert `desk[web]`
        # was in the raw string handed to `notify` — which it was, and the
        # notification still rendered "pip install desk", because `notify`
        # parses markup and ate the bracket. The instruction the message exists
        # to give was the one part guaranteed to go missing.
        rendered = [Content.from_markup(n).plain for n in notes]
        assert any("desk[web]" in r for r in rendered), rendered


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


async def test_x_cancels_a_running_download(monkeypatch):
    """`x` raises the flag the worker's hook reads, so the transfer actually
    stops. The panel promises this in words now, so it must be true."""
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    app = Deck()
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        monkeypatch.setattr(app, "run_worker", lambda *a, **k: None)
        app._start_url_job(URL)
        await pilot.pause()
        assert app._cancel_fetch is False
        await pilot.press("x")
        await pilot.pause()
        assert app._cancel_fetch is True                     # the worker will abort
        assert "cancelling" in _body(app)


async def test_cancelled_download_ends_clean_not_as_an_error(monkeypatch):
    """A cancel is a clean outcome: back to idle, and NO '(error: …)' left
    pinned to the panel the way a real failure is."""
    monkeypatch.setattr(fetch, "AVAILABLE", True)
    def cancelled_fetch(url, **k):
        raise fetch.FetchCancelled("cancelled")
    monkeypatch.setattr(fetch, "fetch_audio", cancelled_fetch)
    app = Deck()
    notes = []
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.notify = lambda *a, **k: notes.append(a[0] if a else "")
        monkeypatch.setattr(app, "call_from_thread", lambda fn, *a, **k: fn(*a, **k))
        app._cancel_fetch = True
        app._run_url_job(URL)
        await pilot.pause()
        assert app._rec_state == "idle" and app._fetch_info == {}
        assert app._cancel_fetch is False                    # reset for the next job
        assert any("cancelled" in n for n in notes)
        assert not any("error" in n.lower() for n in notes)
        assert "(error:" not in (app._last_transcript or "")


async def test_x_during_transcription_says_it_cannot_cancel(monkeypatch):
    """Only the fetch is interruptible — whisper has no safe mid-run abort — so
    the key must say so rather than silently doing nothing."""
    app = Deck()
    notes = []
    async with app.run_test(size=(90, 22)) as pilot:
        await pilot.pause()
        app.notify = lambda *a, **k: notes.append(a[0] if a else "")
        app._rec_state = "transcribing"
        app.action_cancel_job()
        await pilot.pause()
        assert any("can't be cancelled" in n for n in notes)


def test_fetching_panel_advertises_both_keys():
    out = _plain(record.render_fetching({"frac": 0.4, "site": "y"}))
    assert "x cancel" in out                                  # really aborts
    assert "esc hides" in out and "keeps running" in out       # only collapses


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
