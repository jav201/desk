"""The pomodoro journal — the one file that makes yesterday recoverable.

WHY these tests exist: `state.json` carries no timestamp, so before this file
every figure a day-close could show would be invented. The journal is therefore
load-bearing for a whole feature, and it writes to live user state — which is
why "append-only" and "never raises" are tested as hard as the happy path.
"""
from __future__ import annotations

import json

from desk import focus
from desk.app import Deck


def _lines(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]


def test_completed_interval_lands_in_the_journal(tmp_path):
    """AC-1.1: the completing tick is what the day-close counts. If this line
    stops being written, every figure downstream silently becomes fiction."""
    p = focus.Pomodoro(remaining=1)
    p.toggle()
    assert p.tick() is True
    rows = _lines(focus.JOURNAL_PATH)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "completed"
    assert rows[0]["seconds"] == focus.WORK_SECONDS
    assert rows[0]["started_at"] and rows[0]["ended_at"]      # both real stamps


def test_skip_is_recorded_as_a_skip_with_the_time_actually_spent(tmp_path):
    """AC-1.2: a skip is a fact about the day, not an erasure. It carries the
    seconds actually served, so a close can tell 24 minutes abandoned from 20
    seconds abandoned — collapsing both to "skipped" would flatten the day."""
    p = focus.Pomodoro(remaining=focus.WORK_SECONDS - 300)
    p.skip()
    row = _lines(focus.JOURNAL_PATH)[0]
    assert row["outcome"] == "skipped"
    assert row["seconds"] == 300


def test_reset_writes_nothing(tmp_path):
    """`reset` zeroes `completed` — the user declaring the set didn't happen.
    Journalling it would put work in the ledger the user just disowned."""
    p = focus.Pomodoro(remaining=200)
    p.reset()
    assert not focus.JOURNAL_PATH.exists()


def test_the_journal_only_ever_grows(tmp_path):
    """AC-1.3: append-only is the whole safety story for this file. A rewrite
    bug here destroys history that cannot be reconstructed from anywhere else,
    so the earlier bytes are compared verbatim, not just the line count."""
    for _ in range(3):
        focus.Pomodoro(remaining=1, running=True).tick()
    before = focus.JOURNAL_PATH.read_bytes()
    focus.Pomodoro(remaining=1, running=True).tick()
    after = focus.JOURNAL_PATH.read_bytes()
    assert after.startswith(before)                   # nothing rewritten
    assert len(_lines(focus.JOURNAL_PATH)) == 4


def test_first_write_creates_the_directory(tmp_path):
    """AC-1.4: on a fresh machine ~/.desk does not exist yet."""
    target = tmp_path / "brand" / "new" / "pomodoros.jsonl"
    focus.append_journal("completed", 1500, None, path=target)
    assert _lines(target)[0]["outcome"] == "completed"


def test_an_unwritable_journal_never_kills_the_timer(tmp_path):
    """AC-1.5: the timer is the product; the log is bookkeeping. A blocked path
    must cost one line and nothing else — no traceback into Textual's 1 s
    interval, which has no try/except around this call (app.py:_tick)."""
    blocked = tmp_path / "a-file"
    blocked.write_text("not a directory", encoding="utf-8")
    focus.JOURNAL_PATH = blocked / "pomodoros.jsonl"     # mkdir() will raise
    p = focus.Pomodoro(remaining=1)
    p.toggle()
    assert p.tick() is True                              # still completes
    assert not (blocked / "pomodoros.jsonl").exists()


def test_the_record_carries_no_content(tmp_path):
    """The journal is durations and outcomes. It must never grow a field that
    could hold what the user typed, a note path or a project name — those are
    the things that make a log file a privacy problem."""
    rec = focus.append_journal("completed", 1500, None, path=tmp_path / "j.jsonl")
    assert set(rec) == {"started_at", "ended_at", "seconds", "outcome"}


async def test_the_running_deck_writes_one_line_per_interval(tmp_path):
    """The end-to-end seat: through the real app's 1 s tick, not the dataclass
    in isolation. This is the code path the operator's machine actually runs."""
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        app.pomo.remaining = 1
        app._tick()
        await pilot.pause()
        assert app.pomo.remaining == 0
    rows = _lines(focus.JOURNAL_PATH)
    assert len(rows) == 1 and rows[0]["outcome"] == "completed"
