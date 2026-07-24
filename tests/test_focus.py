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


# ---- ember-field redesign ---------------------------------------------------
import re


def _strip(markup: str) -> str:
    return re.sub(r"\[/?[^\]]*\]", "", markup)


def _lit_dots(frac: float) -> int:
    """Count set braille dots across the whole bed for a remaining fraction."""
    total = 0
    for ln in focus.bed_lines(frac):
        for ch in _strip(ln):
            if ch != " ":
                total += bin(ord(ch) - 0x2800).count("1")
    return total


def test_ember_field_mass_tracks_remaining():
    """AC-F2: lit-dot mass is proportional to the remaining fraction, so the
    field visibly drains. This is WHY the panel reads as time-as-substance —
    if a code change decoupled mass from remaining, the metaphor breaks."""
    full = _lit_dots(1.0)
    half = _lit_dots(0.5)
    near_empty = _lit_dots(0.05)
    assert full == 720                       # 30 cols * 2 * 3 rows * 4 = 720
    assert _lit_dots(0.0) == 0               # empty when time is up
    assert full > half > near_empty > 0      # strictly draining
    assert abs(half - 360) <= 1              # ~proportional, not just ordered


def test_ember_field_evaporation_is_stable():
    """The shuffle is seeded, so the dots lit at less time remaining are a subset
    of those lit at more time remaining — dots only disappear, never flicker back.
    Verified through the whole-bed dot count, which must be monotone in frac."""
    counts = [_lit_dots(f / 100) for f in range(0, 101, 5)]
    assert counts == sorted(counts)           # non-decreasing as remaining rises
    assert counts[0] == 0 and counts[-1] == 720


def test_digits_are_bright_not_temperature_tinted():
    """AC-F1: the clock digits use the fixed BRIGHT ink at every remaining value,
    never a temperature hex — legibility must not depend on the timer state."""
    for rem in (focus.WORK_SECONDS, 300, 5):
        body = focus.render_body(focus.Pomodoro(remaining=rem, running=True))
        digit_rows = [l for l in body.splitlines() if focus.BRIGHT in l]
        assert len(digit_rows) == 4                     # 4 braille rows, all bright
        # the temperature hex for this state must not wrap the digits
        assert f"[{focus.temp_hex(1 - rem / focus.WORK_SECONDS)}]" not in "\n".join(digit_rows)


def test_thermometer_and_marker_removed():
    """AC-F3: the old horizontal thermometer legend + ▲ marker are gone."""
    body = focus.render_body(focus.Pomodoro())
    assert "cool" not in body and "hot" not in body
    assert "▲" not in body                          # ▲ marker
    assert not hasattr(focus, "_thermometer")


def test_set_dots_are_neutral_not_temperature():
    """AC-F4: set-progress dots are coded by set position (gold/teal/dim), never
    by the within-interval temperature — so the dots line is invariant to how
    much time is left. Only `completed` (not `remaining`) may change the colours."""
    line = focus.dots_line(completed=2, target=5, state="running")
    assert f"[{focus.DOT_DONE}]●" in line           # done = gold ●
    assert f"[{focus.DOT_NOW}]◐" in line             # current = teal ◐
    assert "[dim]○" in line                          # pending = dim ○
    # the dots row inside render_body must not vary with remaining (no temp coding)
    def dots_row(rem):
        body = focus.render_body(focus.Pomodoro(remaining=rem, completed=2, target=5))
        return next(l for l in body.splitlines() if "○" in l or "◐" in l)
    assert dots_row(focus.WORK_SECONDS) == dots_row(30)   # identical → temperature-free


def test_temperature_ramps_smoothly():
    """The 5-stop palette now interpolates instead of snapping: a fraction
    between two stops yields a colour strictly between them, channel-wise."""
    def rgb(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    lo, mid, hi = rgb(focus.temp_hex(0.0)), rgb(focus.temp_hex(0.125)), rgb(focus.temp_hex(0.25))
    assert lo != mid != hi                               # not snapped to a band
    # green channel moves monotonically from #45c4ff -> #34d1bf across the band
    assert lo[1] <= mid[1] <= hi[1]
