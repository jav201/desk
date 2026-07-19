"""Capture: daily-note append (create note, create/reuse heading, insert before
later sections, missing vault), prompt rotation, markup safety, Deck write."""
from __future__ import annotations

from datetime import datetime

import pytest

from desk import capture
from desk.app import Deck

NOW = datetime(2026, 7, 19, 15, 42)


def _cfg(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    return {"vault": v, "daily_subdir": "Daily"}


def test_creates_note_and_heading(tmp_path):
    note = capture.append_capture("ship the deck", cfg=_cfg(tmp_path), now=NOW)
    assert note.name == "2026-07-19.md"
    text = note.read_text(encoding="utf-8")
    assert "# 2026-07-19" in text
    assert "## Captures" in text
    assert "- 2026-07-19 15:42  ship the deck" in text


def test_appends_under_one_heading_in_order(tmp_path):
    cfg = _cfg(tmp_path)
    capture.append_capture("first", cfg=cfg, now=NOW)
    note = capture.append_capture("second", cfg=cfg, now=datetime(2026, 7, 19, 16, 0))
    text = note.read_text(encoding="utf-8")
    assert text.count("## Captures") == 1
    assert text.index("first") < text.index("second")


def test_inserts_before_a_later_section(tmp_path):
    cfg = _cfg(tmp_path)
    note = cfg["vault"] / "Daily" / "2026-07-19.md"
    note.parent.mkdir(parents=True)
    note.write_text("# 2026-07-19\n\n## Captures\n- old\n\n## Log\n- stuff\n", encoding="utf-8")
    capture.append_capture("new one", cfg=cfg, now=NOW)
    lines = note.read_text(encoding="utf-8").splitlines()
    new_i = next(i for i, l in enumerate(lines) if "new one" in l)
    old_i = next(i for i, l in enumerate(lines) if l == "- old")
    cap_i = lines.index("## Captures")
    log_i = lines.index("## Log")
    assert cap_i < old_i < new_i < log_i


def test_missing_vault_raises(tmp_path):
    cfg = {"vault": tmp_path / "nope", "daily_subdir": "Daily"}
    with pytest.raises(FileNotFoundError):
        capture.append_capture("x", cfg=cfg, now=NOW)


def test_prompt_rotates():
    assert capture.pick_prompt(0) == capture.PROMPTS[0]
    assert capture.pick_prompt(len(capture.PROMPTS)) == capture.PROMPTS[0]


def test_body_escapes_markup():
    assert "\\[red]" in capture.render_body("[red]x[/red]")


async def test_deck_capture_writes(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    v.mkdir()
    monkeypatch.setattr(capture, "load_config",
                        lambda path=None: {"vault": v, "daily_subdir": "Daily"})
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        inp = app.query_one("#cap-input")
        inp.value = "hello from the deck"
        from textual.widgets import Input
        inp.post_message(Input.Submitted(inp, inp.value, None))
        await pilot.pause()
        notes = list((v / "Daily").glob("*.md"))
        assert notes and "hello from the deck" in notes[0].read_text(encoding="utf-8")
