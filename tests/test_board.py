"""Board panel: parsing board.json, current-doing detection, ordered render,
markup safety, and the Deck integration."""
from __future__ import annotations

import json

import pytest
from test_markup_safety import assert_inert

from desk import board
from desk.app import Deck

SAMPLE = {
    "projects": [{"id": "p1", "name": "Web"}, {"id": "p2", "name": "Mobile"}],
    "tasks": [
        {"id": "t1", "title": "renew TLS", "project_id": None, "status": "backlog", "priority": "high"},
        {"id": "t2", "title": "funnel copy", "project_id": "p1", "status": "doing", "priority": "normal"},
        {"id": "t3", "title": "CI pipeline", "project_id": "p2", "status": "done", "priority": "low"},
        {"id": "t4", "title": "archived one", "project_id": "p1", "status": "doing", "archived": True},
    ],
    "settings": {},
}


def _write(tmp_path, data):
    p = tmp_path / "board.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_load_missing_returns_none(tmp_path):
    assert board.load(tmp_path / "nope.json") is None


def test_current_doing_skips_archived(tmp_path):
    d = board.load(_write(tmp_path, SAMPLE))
    assert board.current_doing(d)["id"] == "t2"      # t4 is doing but archived


def test_legacy_active_counts_as_doing(tmp_path):
    data = {"projects": [], "tasks": [{"id": "x", "title": "old", "status": "active"}], "settings": {}}
    d = board.load(_write(tmp_path, data))
    assert board.current_doing(d)["id"] == "x"


def test_tile_shows_current(tmp_path):
    d = board.load(_write(tmp_path, SAMPLE))
    tile = board.render_tile(d)
    assert "Web" in tile and "funnel copy" in tile


def test_tile_no_board():
    assert "no board loaded" in board.render_tile(None)


import re


def _plain(markup: str) -> str:
    """Visible text with Textual tags stripped — the header styles the label and
    count separately, so assert against the rendered text, not the raw markup."""
    return re.sub(r"\[/?[^\]]*\]", "", markup)


def test_body_has_columns_and_counts(tmp_path):
    d = board.load(_write(tmp_path, SAMPLE))
    plain = _plain(board.render_body(d))
    assert "TODO 1" in plain and "DOING 1" in plain and "DONE 1" in plain
    assert "funnel copy" in plain              # the doing task appears in the NOW banner


@pytest.mark.parametrize("payload", ["[red]boom[/red]", "[Bold]boom[/]",
                                     "[$accent]boom[/]", "[_x]boom[/]"])
def test_body_escapes_markup(tmp_path, payload):
    """A task title comes out of `~/.taskboard/board.json` — a file desk neither
    writes nor validates — and lands in a markup language.

    THE ORACLE IS THE PARSER. This used to assert `"\\\\[red]" in body`, which
    proves `esc()` ran and nothing more: it stayed green while the output was
    still live, because it never asked Textual what the string MEANS. The last
    three payloads are exactly the ones rich's escape lets through — they were
    passing that old assertion and rendering as real styles."""
    def render(title):
        data = {"projects": [],
                "tasks": [{"id": "m", "title": title, "status": "backlog"}],
                "settings": {}}
        return board.render_body(board.load(_write(tmp_path, data)))
    assert_inert(render, payload, "board.render_body")


async def test_deck_board_panel(tmp_path, monkeypatch):
    monkeypatch.setattr(board, "BOARD_PATH", _write(tmp_path, SAMPLE))
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("b")
        await pilot.pause()
        body = str(app.query_one("#stage-body").render())
        assert "funnel copy" in body
        tile = str(app.query_one("#tile-board").render())
        assert "funnel copy" in tile


# ---- phase schema + rescue layer (mission-control redesign) -----------------
PHASE_BOARD = {
    "phases": ["Backlog", "Doing", "Done"],
    "projects": [{"id": "p1", "name": "GRNDIA", "color": "amber"}],
    "tasks": [
        {"id": "a", "title": "ship", "project_id": "p1", "phase": "Doing",
         "priority": "high", "due_date": "2026-07-26"},
        {"id": "b", "title": "queued", "project_id": "p1", "phase": "Backlog",
         "priority": "normal", "due_date": "2026-08-01"},
        {"id": "c", "title": "shipped", "project_id": "p1", "phase": "Done"},
    ],
    "settings": {},
}


def test_reads_phase_schema_not_just_status(tmp_path):
    """The real board dropped `status` for `phase`; desk must count those tasks
    (the bug this redesign fixes: a phase-only board rendered zero tasks)."""
    d = board.load(_write(tmp_path, PHASE_BOARD))
    tasks, phases, _ = board.normalize(d)
    todo, doing, done = board._buckets(tasks, phases)
    assert (len(todo), len(doing), len(done)) == (1, 1, 1)
    assert board.current_doing(d)["id"] == "a"          # phase "Doing" == now


def test_normalize_rescues_drifted_tasks_never_drops():
    """A task with a missing title / unknown phase / a bare non-object entry must
    be rescued (kept, with a placeholder) — work never silently leaves the board."""
    data = {"phases": ["Backlog", "Doing", "Done"], "projects": [], "tasks": [
        {"id": "ok", "title": "fine", "phase": "Doing"},
        {"id": "notitle", "phase": "Backlog"},                 # missing title
        {"id": "nophase", "title": "orphan"},                  # no phase/status
        "i am not an object",                                   # garbage entry
    ]}
    tasks, _, report = board.normalize(data)
    assert report["total"] == 4
    assert len(tasks) == 3                                     # 3 objects kept
    assert report["dropped"] == 1                             # only the non-object
    titles = {t["id"]: t["title"] for t in tasks}
    assert titles["notitle"] == "(untitled)"                  # title rescued
    assert next(t for t in tasks if t["id"] == "nophase")["phase"] == "Backlog"
    assert report["rescued"] == 2                             # notitle + nophase


def test_validate_reports_health_without_render():
    assert board.validate(None)["total"] == 0
    ok = board.validate(PHASE_BOARD)
    assert ok["total"] == 3 and ok["rescued"] == 0 and ok["dropped"] == 0


def test_horizon_places_overdue_and_future_due(tmp_path):
    """Overdue tasks mass left of the today-rule; future dues sit on their day."""
    data = {"phases": ["Backlog", "Doing", "Done"], "projects": [],
            "tasks": [
                {"id": "od", "title": "late", "phase": "Backlog", "due_date": "2026-07-20"},
                {"id": "fut", "title": "soon", "phase": "Backlog", "due_date": "2026-07-28"},
            ]}
    d = board.load(_write(tmp_path, data))
    plain = _plain(board.render_body(d, today=__import__("datetime").date(2026, 7, 24)))
    assert "overdue" in plain                                 # overdue chip present
    assert "▲" in plain and "│" in plain                      # overdue mark + today rule
    assert "●" in plain                                       # a future due dot rendered


def test_ledger_progress_and_project_colour(tmp_path):
    d = board.load(_write(tmp_path, PHASE_BOARD))
    body = board.render_body(d, today=__import__("datetime").date(2026, 7, 24))
    assert "#fbbf24" in body                                  # amber project spine/bar
    assert "1/3" in _plain(body)                              # GRNDIA: 1 done of 3


def test_now_pulses_on_beat_when_a_task_is_doing(tmp_path):
    """D1: the NOW element (strip tile + hero banner) gets a project-tinted
    background wash on a beat while a task is in progress, so the deck breathes.
    A board with nothing in progress never pulses."""
    import datetime
    d = board.load(_write(tmp_path, PHASE_BOARD))               # has a Doing task
    assert board.render_tile(d, beat=True) != board.render_tile(d, beat=False)
    assert "[on #" in board.render_tile(d, beat=True)           # bg wash present
    today = datetime.date(2026, 7, 24)
    assert board.render_body(d, today=today, beat=True) != board.render_body(d, today=today, beat=False)
    nodoing = {"phases": ["Backlog", "Doing", "Done"], "projects": [],
               "tasks": [{"id": "x", "title": "queued", "phase": "Backlog"}]}
    dn = board.load(_write(tmp_path, nodoing))
    assert board.render_tile(dn, beat=True) == board.render_tile(dn, beat=False)


def test_body_marks_rescued_tasks(tmp_path):
    data = {"phases": ["Backlog", "Doing", "Done"], "projects": [],
            "tasks": [{"id": "x", "phase": "Doing"}]}          # missing title -> rescued
    d = board.load(_write(tmp_path, data))
    assert "rescued" in _plain(board.render_body(d))


async def test_refresh_reloads_board_immediately(tmp_path, monkeypatch):
    """F5 picks up an external change to board.json without waiting for the poll."""
    import json
    p = tmp_path / "board.json"
    p.write_text(json.dumps(
        {"projects": [], "tasks": [{"id": "a", "title": "first", "status": "doing"}], "settings": {}}),
        encoding="utf-8")
    monkeypatch.setattr(board, "BOARD_PATH", p)
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "first" in str(app.query_one("#tile-board").render())
        p.write_text(json.dumps(
            {"projects": [], "tasks": [{"id": "b", "title": "second", "status": "doing"}], "settings": {}}),
            encoding="utf-8")
        await pilot.press("f5")
        await pilot.pause()
        assert "second" in str(app.query_one("#tile-board").render())
