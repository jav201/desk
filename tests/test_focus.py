"""Focus/pomodoro: state machine, braille render, persistence, and the Deck
integration (space starts it, a tick counts down)."""
from __future__ import annotations

from desk import focus
from desk.app import Deck


def test_state_machine_run_complete():
    p = focus.Pomodoro(remaining=3)
    p.toggle()                                  # start
    assert p.running
    assert p.tick() is False and p.remaining == 2
    assert p.tick() is False and p.remaining == 1
    assert p.tick() is True                      # completing tick
    assert p.remaining == 0 and p.running is False and p.completed == 1


def test_skip_and_reset():
    p = focus.Pomodoro()
    p.skip()
    assert p.completed == 1 and p.remaining == focus.WORK_SECONDS and not p.running
    p.reset()
    assert p.completed == 0 and p.remaining == focus.WORK_SECONDS and not p.running


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    p = focus.Pomodoro(remaining=1234, running=True, completed=2)
    p.save(path)
    q = focus.Pomodoro.load(path)
    assert (q.remaining, q.running, q.completed) == (1234, True, 2)


def test_load_missing_is_fresh(tmp_path):
    q = focus.Pomodoro.load(tmp_path / "nope.json")
    assert q.remaining == focus.WORK_SECONDS and not q.running and q.completed == 0


def test_braille_lines_equal_width():
    lines = focus.braille_lines("25:00")
    assert len(lines) == 4
    assert len({len(l) for l in lines}) == 1     # all rows same width


def test_temperature_warms():
    assert focus.temp_hex(0.0) == "#45c4ff"      # cool when fresh
    assert focus.temp_hex(1.0) == "#ff3b30"      # hot when done


async def test_deck_space_starts_pomodoro(tmp_path, monkeypatch):
    """space starts the timer and a tick counts it down, through the real app."""
    monkeypatch.setattr(focus, "STATE_PATH", tmp_path / "state.json")
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.pomo.running is False
        await pilot.press("space")
        await pilot.pause()
        assert app.pomo.running is True
        before = app.pomo.remaining
        app._tick()
        assert app.pomo.remaining == before - 1
        # the focus tile reflects the running mark
        tile = str(app.query_one("#tile-focus").render())
        assert "▸" in tile


def test_target_add_remove_floor_ceiling_and_persist(tmp_path):
    p = focus.Pomodoro()
    assert p.target == focus.POMO_SET
    p.add()
    assert p.target == focus.POMO_SET + 1
    for _ in range(30):
        p.add()
    assert p.target == focus.POMO_MAX                 # capped
    for _ in range(30):
        p.remove()
    assert p.target == 1                               # floored
    q = focus.Pomodoro(completed=3, target=3)
    q.remove()
    assert q.target == 2 and q.completed == 2          # completed clamps with target
    path = tmp_path / "s.json"
    focus.Pomodoro(target=8, completed=2).save(path)
    assert focus.Pomodoro.load(path).target == 8       # target round-trips


def test_render_uses_target_not_fixed_five():
    assert "of 3" in focus.render_body(focus.Pomodoro(target=3))
