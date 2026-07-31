"""Nothing desk did not write may become an instruction.

A web video's title arrives over the network. A filename comes off a disk this
app does not own. A whisper transcript is whatever was said. All three used to
be interpolated straight into markup, and markup is not decoration — it is a
small language with an action verb in it.

THE ORACLE HERE IS THE PARSER, NOT A SUBSTRING. `tests/test_board.py:73` asserts
`"\\[red]" in body`, which proves `esc()` ran and nothing else: it stays green
while the output is still live, because it never asks Textual what the string
MEANS. Every law below parses the rendered markup and asserts two things — the
payload survives as literal characters, and no span carrying a style or an
action was created. A test that cannot see a live span cannot see this bug.
"""
from __future__ import annotations

import re

import pytest
from textual.content import Content

from desk import picker, record
from desk.markup import esc

# Each payload is a real capability, not a shape. The last three are the ones
# `rich.markup.escape` lets through: its regex only fires on `[` followed by
# a-z, `#`, `/` or `@`, while Textual opens a tag on ANY `[`.
INJECTIONS = {
    "action": "[@click=app.quit]HERE[/]",     # dispatches into desk's actions
    "orphan_close": "[/]",                    # raised out of the compositor
    "lowercase": "[red]x[/red]",
    "nested": "[red][bold]deep[/bold][/red]",
    "uppercase": "[Bold]X[/]",                # survives rich's escape
    "underscore": "[_x]y[/]",                 # survives rich's escape
    "variable": "[$accent]X[/]",              # survives rich's escape
    "bracket_run": "[[double]]",
    "lone_open": "an unclosed [ bracket",
}
# A benign control of the same shape. The oracle is a COMPARISON, never a list
# of forbidden style names: desk's own styles are things like `bold #2dd4bf`,
# so any substring check for "bold" flags the app's own chrome and the law
# becomes noise. Two renders, identical everywhere but the payload, must
# produce the identical set of styles — anything extra was authored by the
# payload, whatever it is called.
BENIGN = "SAFEPAYLOAD"

# The same payloads with their closing tags removed, so they can be filenames.
# An OPENING tag is what creates a span, so these inject just as hard. `[/]` is
# nothing BUT a closing tag, so it strips to the empty string and is declared
# out rather than quietly becoming a file called ".m4a" that tests nothing.
FILE_SAFE = {n: s for n, s in
             ((n, re.sub(r"\[/[^\]]*\]", "", p)) for n, p in INJECTIONS.items())
             if s.strip()}
NOT_A_FILENAME = {"orphan_close"}


def test_the_filename_payloads_are_still_injections():
    """C-31: the derived set is an oracle of its own. Strip too much and the
    picker law below renders harmless strings while staying green — which is
    exactly what happened: `[/]` came out empty and the law could not see it."""
    assert set(INJECTIONS) - set(FILE_SAFE) == NOT_A_FILENAME
    for name, p in FILE_SAFE.items():
        assert "/" not in p, f"{name} still cannot be a filename: {p!r}"
        assert "[" in p, f"{name} lost its opening tag and injects nothing: {p!r}"


def _styles(rendered, where: str) -> tuple[list[str], str]:
    """`rendered` is either markup awaiting a parse, or a widget's already-parsed
    `Content`. The distinction matters: a widget has ALREADY consumed its markup,
    so its plain text legitimately holds a literal `[Bold]` — and re-parsing that
    conjures the very span the law is looking for. Double-parsing turns a correct
    escape into a failure, which is how this helper first read the picker."""
    try:
        content = (rendered if isinstance(rendered, Content)
                   else Content.from_markup(rendered))
    except Exception as exc:                      # a bare [/] used to land here
        pytest.fail(f"{where}: rendering raised {type(exc).__name__}: {exc}")
    return sorted(str(s.style) for s in content.spans), content.plain


def assert_inert(render, payload: str, where: str, expect=None) -> None:
    """`render(text) -> markup`. The payload reached the screen as characters
    and created no style the benign control did not also create."""
    hostile_styles, plain = _styles(render(payload), where)
    control_styles, _ = _styles(render(BENIGN), where + "/control")
    assert hostile_styles == control_styles, (
        f"{where}: the payload authored styles of its own\n"
        f"  with payload: {hostile_styles}\n"
        f"  with benign : {control_styles}")
    want = payload if expect is None else expect
    assert want in plain, (
        f"{where}: payload did not survive as text\n"
        f"  sent: {want!r}\n  got : {plain!r}")


# ---- the helper itself ------------------------------------------------------
@pytest.mark.parametrize("name", sorted(INJECTIONS))
def test_the_escape_renders_every_payload_as_characters(name):
    """The law at its source, inside desk's own wrapper — the escape has to
    survive being adjacent to a real tag, which is where it is always used."""
    payload = INJECTIONS[name]
    assert_inert(lambda t: f"[dim]{esc(t)}[/dim]", payload, f"esc/{name}")


def test_the_escape_is_stronger_than_the_one_it_replaced():
    """THE RECEIPT, and the reason this module exists rather than an import.

    `rich.markup.escape` is the obvious choice and it is not sufficient here,
    because desk renders through Textual's parser and the two disagree about
    what opens a tag. If this ever stops failing, rich's escape has been fixed
    and `desk/markup.py` can go — but until then, swapping back is a regression
    the rest of this file would catch only by luck."""
    from rich.markup import escape as rich_esc
    base, _ = _styles(f"[dim]{rich_esc(BENIGN)}[/dim]", "rich/control")
    leaked = []
    for name, payload in INJECTIONS.items():
        got, _ = _styles(f"[dim]{rich_esc(payload)}[/dim]", f"rich/{name}")
        if got != base:
            leaked.append(name)
    assert set(leaked) == {"uppercase", "underscore", "variable"}, (
        f"rich's escape now leaks {leaked} — the measured basis of desk/markup.py "
        "has changed and the module's claim needs re-measuring")


# ---- record: the network-sourced sinks (the HIGHs) --------------------------
@pytest.mark.parametrize("name", sorted(INJECTIONS))
@pytest.mark.parametrize("field", ["title", "url", "status", "site"])
def test_a_hostile_video_title_is_inert(name, field):
    """A yt-dlp title is chosen by whoever uploaded the video. `[@click=…]` made
    it a clickable link into desk's action namespace; `[/]` crashed the deck on
    every repaint, permanently, from one character."""
    payload = INJECTIONS[name]
    # `frac` picks the branch: None is the probe (which is the only place the
    # URL is drawn), a number is the download. Rendering the wrong branch makes
    # the payload absent and the law green for the wrong reason.
    info = {"url": "https://x/y", "site": "yt", "title": "ok",
            "duration": 61, "status": "downloading…",
            "frac": None if field == "url" else 0.5}

    def render(text):
        got = dict(info)
        got[field] = text
        return record.render_fetching(got, phase=1)
    assert_inert(render, payload, f"render_fetching/{field}/{name}")


@pytest.mark.parametrize("name", sorted(INJECTIONS))
def test_a_hostile_transcript_preview_is_inert(name):
    """The preview is whisper's output — whatever was said, or the text of a
    yt-dlp failure, which carries the remote URL inside it."""
    payload = INJECTIONS[name]
    assert_inert(lambda t: record.render_body("idle", last=t), payload,
                 f"render_body/last/{name}")


@pytest.mark.parametrize("name", sorted(INJECTIONS))
def test_a_hostile_whisper_model_name_is_inert(name, monkeypatch):
    """`DESK_WHISPER_MODEL` is read from the environment (`transcribe.py:22`)."""
    payload = INJECTIONS[name]
    from desk import transcribe
    monkeypatch.setattr(record, "AVAILABLE", True)

    def render(text):
        monkeypatch.setattr(transcribe, "DEFAULT_MODEL", text, raising=False)
        return record.render_body("idle")
    assert_inert(render, payload, f"whisper_label/{name}")


# ---- picker: the disk-sourced sink ------------------------------------------
@pytest.mark.parametrize("name", sorted(FILE_SAFE))
async def test_a_hostile_filename_is_inert(name, tmp_path):
    """A filename is attacker-controlled the moment desk browses a directory it
    did not create — a downloads folder, a shared drive, an extracted archive."""
    # A filename cannot contain `/` on any platform desk runs on, so the raw
    # payloads would skip 7 of 9 cases here — on the sink that browses other
    # people's disks. The CLOSING tag is what carries the slash and it is not
    # what creates a span, so drop it: `[@click=app.quit]HERE` injects exactly
    # as well as `[@click=app.quit]HERE[/]` does. Derived from INJECTIONS, never
    # hand-listed, so a payload added there is covered here too.
    payload = FILE_SAFE[name]
    from desk.app import Deck

    async def browse(text: str) -> str:
        """One directory holding exactly one file, named `text`."""
        d = tmp_path / f"browse{abs(hash(text))}"
        d.mkdir()
        (d / f"{text}.m4a").write_bytes(b"")
        app = Deck()
        async with app.run_test(size=(90, 30)) as pilot:
            await pilot.pause()
            app.push_screen(picker.AudioPicker(start=d))
            await pilot.pause()
            await pilot.pause()
            # the Content itself, not str() of it — see `_styles`
            return app.screen.query_one("#pick-body").render()

    try:
        hostile, control = await browse(payload), await browse(BENIGN)
    except OSError:
        pytest.skip("this filesystem rejects the payload as a filename")
    # the two listings differ ONLY in the one filename, so any style the
    # hostile frame carries and the control does not was authored by the name
    assert_inert(lambda t: hostile if t is payload else control, payload,
                 f"picker/{name}", expect=_tail(payload))


def _tail(payload: str) -> str:
    """`_fit` keeps the TAIL of an over-long string, so assert only what the
    widget actually had room to draw."""
    return payload[-20:] if len(payload) > 20 else payload


@pytest.mark.parametrize("name", sorted(INJECTIONS))
def test_a_hostile_url_in_the_link_card_is_inert(name):
    """The URL comes from the operator's clipboard, which is not the same thing
    as the operator having typed it."""
    payload = INJECTIONS[name]
    assert_inert(
        lambda t: "\n".join(picker.AudioPicker()._link_card("https://host/" + t)),
        payload, f"link_card/{name}", expect=_tail(payload))


# ---- app: the notification sink ---------------------------------------------
@pytest.mark.parametrize("name", sorted(INJECTIONS))
async def test_a_hostile_failure_message_is_inert(name):
    """`notify` parses markup too. A transcription failure carries yt-dlp's own
    error text, and yt-dlp puts the remote URL and server response in it."""
    payload = INJECTIONS[name]
    from desk.app import Deck
    app = Deck()
    sent = []
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.notify = lambda *a, **k: sent.append(a[0] if a else "")
        app._on_transcribed(None, payload)
        app._on_transcribed(None, BENIGN)
        await pilot.pause()
    assert len(sent) == 2, sent
    # the oracle is what the parser does to the string that REACHED notify
    assert_inert(lambda t: sent[0] if t is payload else sent[1], payload,
                 f"notify/{name}")


def test_the_card_seat_carries_the_escape_too():
    """`render_card` is a second render path for the same data, and it escapes
    through the same helper — this pins that it is the same helper, not a
    second one that could drift."""
    import desk.record as r
    assert r.esc is esc, "record.py stopped using desk/markup.py's escape"
    import desk.picker as p
    assert p.esc is esc, "picker.py stopped using desk/markup.py's escape"
