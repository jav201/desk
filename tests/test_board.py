"""Board panel: parsing board.json, current-doing detection, ordered render,
markup safety, and the Deck integration."""
from __future__ import annotations

import json

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


def test_body_has_columns_and_counts(tmp_path):
    d = board.load(_write(tmp_path, SAMPLE))
    body = board.render_body(d)
    assert "TODO 1" in body and "DOING 1" in body and "DONE 1" in body
    assert "funnel copy" in body


def test_body_escapes_markup(tmp_path):
    data = {"projects": [], "tasks": [{"id": "m", "title": "[red]boom[/red]", "status": "backlog"}], "settings": {}}
    d = board.load(_write(tmp_path, data))
    body = board.render_body(d)
    assert "\\[red]" in body                          # escaped -> won't crash markup


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
