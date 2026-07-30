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

from desk import focus


@pytest.fixture(autouse=True)
def _isolate_desk_state(tmp_path, monkeypatch):
    monkeypatch.setattr(focus, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(focus, "JOURNAL_PATH", tmp_path / "pomodoros.jsonl")
    return tmp_path
