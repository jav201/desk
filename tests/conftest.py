"""Keep the whole suite off the operator's real ~/.desk.

Two paths in `focus` point at live user state. Until now each test that cared
redirected `STATE_PATH` for itself, and the several `Deck()` tests that did not
were quietly saving over the operator's running timer. `JOURNAL_PATH` makes that
worse: the pomodoro journal is append-only, so a test run would not overwrite it
— it would permanently pollute it with fake intervals.

Autouse, so a test cannot forget.
"""
from __future__ import annotations

import pytest

from desk import board, capture, focus, record


@pytest.fixture(autouse=True)
def _isolate_desk_state(tmp_path, monkeypatch):
    """Every path in the package that points at live user state.

    The first version covered only `focus`, while its docstring claimed the
    whole suite — which is the exact failure it was written to fix. The sharpest
    one left open: `Deck.on_input_submitted` calls `capture.append_capture()`
    with no config, which resolves to the operator's real Obsidian vault. No
    test drives a capture submit through the pilot today, so it was latent
    rather than live; a test written next week would not have known that."""
    monkeypatch.setattr(focus, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(focus, "JOURNAL_PATH", tmp_path / "pomodoros.jsonl")
    monkeypatch.setattr(focus, "JOURNAL_ERROR", None)
    monkeypatch.setattr(capture, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(capture, "FALLBACK_PATH", tmp_path / "captures.md")
    monkeypatch.setattr(capture, "DEFAULT_VAULT", tmp_path / "vault")
    monkeypatch.setattr(record, "RECORD_SETTINGS_PATH", tmp_path / "record.json")
    monkeypatch.setattr(record, "TRANSCRIPTS_DIR", tmp_path / "transcripts")
    monkeypatch.setattr(board, "BOARD_PATH", tmp_path / "board.json")
    return tmp_path
