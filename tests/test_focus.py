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
import random
import re


def _strip(markup: str) -> str:
    return re.sub(r"\[/?[^\]]*\]", "", markup)


def _hearth_dots(frac: float, ts: str = "25:00") -> int:
    """Count set braille dots across the whole hearth (field + carved digits)."""
    total = 0
    for ln in focus.hearth_lines(frac, ts):
        for ch in _strip(ln):
            if ch != " ":
                total += bin(ord(ch) - 0x2800).count("1")
    return total


def test_hearth_field_drains_with_remaining():
    """AC-F2 (hearth): the whole-panel fire's lit mass falls as time runs down,
    burning to a floor of just the carved digits. If a change decoupled the mass
    from remaining, the 'time as fire' metaphor breaks."""
    full, half, empty = _hearth_dots(1.0), _hearth_dots(0.5), _hearth_dots(0.0)
    assert full > half > empty > 0            # digits are the floor; field burns down
    seq = [_hearth_dots(f / 100) for f in range(0, 101, 10)]
    assert seq == sorted(seq)                 # monotone: dots only disappear over time


def test_hearth_evaporation_is_stable():
    """The front is a deterministic function of `remaining_frac`, so the fire
    only ever recedes as time runs down; it never flickers back up."""
    counts = [_hearth_dots(f / 100) for f in range(0, 101, 5)]
    assert counts == sorted(counts)


# ---- ordered coverage: the ember is a BOUNDARY, not a scatter ---------------
def _fire_cells(frac: float, phase: int = 0) -> int:
    """Cells the renderer painted as FIRE — tone neither ash nor digit ink.

    The oracle asks the renderer's own output what it painted rather than
    re-deriving the geometry, so it cannot drift into agreeing with a broken
    renderer by sharing its bug."""
    n = 0
    for ln in focus.hearth_lines(frac, "", phase=phase):
        for m in re.finditer(r"\[([^\]/][^\]]*)\]([^\[]*)", ln):
            if m.group(1) in (focus.EMBER, focus.BRIGHT):
                continue
            n += sum(1 for c in m.group(2) if c != " ")
    return n


def test_the_ember_reads_as_draining_all_the_way_down():
    """THE POINT OF THE PANEL. A quantity scattered at random over a braille
    field is invisible until it nears zero — 8 dots to a cell means the odds of
    a cell going dark are (1-frac)**8. Encoded as a moving front instead, the
    fire has to look different at 90 % and at 50 %, which is the whole reason
    anyone watches it. Measured on painted CELLS, which is what an eye reads."""
    got = [_fire_cells(f) for f in (0.9, 0.5, 0.1)]
    assert got[0] > got[1] > got[2], f"not monotone: {got}"
    assert got[0] / got[2] >= 3.0, f"range too flat: {got}"
    assert got[0] - got[1] > 50, f"90 % and 50 % are indistinguishable: {got}"


def test_the_old_shuffle_drain_would_fail_that_law():
    """THE CONTROL, and the reason the law above is not decoration: it
    re-implements the drain desk actually shipped and asserts the law can see
    the defect it was written for. A law whose only evidence is that the new
    code passes has never been shown capable of failing."""
    def shuffled(frac, rows=focus.HEARTH_ROWS, cols=focus.HEARTH_COLS):
        W, H = cols * 2, rows * 4
        order = [(x, y) for y in range(H) for x in range(W)]
        random.Random(focus.BED_SEED).shuffle(order)
        lit = set(order[:round(frac * len(order))])
        return sum(1 for cy in range(rows) for cx in range(cols)
                   if any((cx * 2 + x, cy * 4 + y) in lit
                          for y in range(4) for x in range(2)))
    got = [shuffled(f) for f in (0.9, 0.5, 0.1)]
    assert got[0] / got[2] < 3.0 or got[0] - got[1] <= 50, (
        f"the shipped shuffle would PASS ({got}) — the law is blind")


def test_ordered_at_every_breath_phase():
    """A field that only reads correctly on one frame of its own animation is
    not ordered — the user sees whichever frame they happen to look at."""
    for p in range(4):
        got = [_fire_cells(f, phase=p) for f in (0.9, 0.5, 0.1)]
        assert got[0] > got[1] > got[2], f"phase {p}: {got}"


def test_the_breath_moves_the_shape_and_cannot_move_the_datum():
    """LIFE AND DATA ARE SEPARATE CHANNELS. The front's mean height is the
    remaining fraction; its raggedness is the breath. Each column carries an
    independent random phase, so across 60 of them the jitter averages out and
    a phase rotation cannot edit the reading — the ambient cannot lie about the
    time left.

    Measured against the DATUM itself, not merely against the other phases: a
    front that drifted the same way at every phase would satisfy a
    phase-to-phase comparison while reading the wrong time all day."""
    datum = (1.0 - 0.5) * 36                      # the height the fraction means
    for p in range(8):
        mean = sum(focus._flame_line(60, 36, 0.5, p)) / 60
        assert abs(mean - datum) < focus.HEARTH_JIT / 4, (p, mean, datum)
    shapes = {_strip("".join(focus.hearth_lines(0.5, "", phase=p)))
              for p in range(4)}
    assert len(shapes) == 4          # a breath that changes nothing is a timer


def _ash_by_row(frac: float) -> list[int]:
    """Cells painted as ash, per cell-row. Uncarved, so the clock's fixed
    subtraction cannot be mistaken for a change in the smoke."""
    out = []
    for ln in focus.hearth_lines(frac, ""):
        n = 0
        for m in re.finditer(rf"\[{re.escape(focus.EMBER)}\]([^\[]*)", ln):
            n += sum(1 for c in m.group(1) if c != " ")
        out.append(n)
    return out


def test_the_spent_field_leaves_ash_that_thins_with_height():
    """GROUND. What the fire has already eaten is not blank — it is smoke, dense
    at the burn line and thinning upward. It carries NO datum; it is there
    because a background wants surface, and deleting it (the obvious
    'simplification') leaves a panel that is 70 % empty rows and reads dead.
    The gradient is the point: a flat stipple would read as wallpaper."""
    rows = _ash_by_row(0.1)                # front low, most of the panel spent
    assert sum(rows) > 40, f"no ash above the front: {rows}"
    near, far = rows[7], rows[0]           # just above the front vs the far top
    assert near > far, f"smoke does not thin with height: {rows}"


def test_the_carved_counter_never_flickers():
    """The digits are the one thing on the panel that must be trusted at a
    glance. The fire moves past them; they do not move. Compared on the digit
    cells only — the field inside those rows is supposed to change."""
    def digits(phase):
        out = []
        for ln in focus.hearth_lines(0.5, "12:34", phase=phase):
            out += [m.group(1) for m in
                    re.finditer(rf"\[{re.escape(focus.BRIGHT)}\]([^\[]*)", ln)]
        return out
    assert len({tuple(digits(p)) for p in range(4)}) == 1


def test_the_ember_looks_different_at_calm_typical_and_extreme():
    """Three states, three pictures. Two states that render alike are a dead
    channel, and 'running out' is the one state that most has to have a face."""
    seen = {}
    for name, rem in (("calm", 1500), ("typical", 700), ("extreme", 45)):
        key = _strip("\n".join(focus.hearth_lines(rem / focus.WORK_SECONDS,
                                                  focus.mmss(rem))))
        assert key not in seen, f"identical at {seen.get(key)} and {name}"
        seen[key] = name


def test_hearth_rows_are_width_exact():
    """Every hearth row shares one visible width and uses only width-1 glyphs, so
    the fire never desynchronises the panel."""
    import unicodedata
    lines = focus.hearth_lines(0.5, "25:00")
    assert len(lines) == focus.HEARTH_ROWS
    assert len({len(_strip(l)) for l in lines}) == 1
    for l in lines:
        for ch in _strip(l):
            assert unicodedata.east_asian_width(ch) not in ("W", "F"), repr(ch)


def test_clock_is_carved_bright_over_the_fire():
    """AC-F1 (hearth): the clock digits render at full BRIGHT independent of the
    timer state, carved into the field so they stay legible over the fire. The
    clock spans exactly the 4 cell-rows below the top band."""
    for rem in (focus.WORK_SECONDS, 300, 5):
        lines = focus.hearth_lines(rem / focus.WORK_SECONDS, focus.mmss(rem))
        bright_rows = [i for i, l in enumerate(lines) if f"[{focus.BRIGHT}]" in l]
        assert bright_rows == [2, 3, 4, 5]              # the carved clock band
    # digit ink is constant: BRIGHT present in the band at full AND near-empty
    for frac in (1.0, 0.05):
        band = focus.hearth_lines(frac, "25:00")[2:6]
        assert all(f"[{focus.BRIGHT}]" in r for r in band)


def test_running_timer_breathes_but_digits_do_not():
    """The field brightens on a beat so a running timer feels alive; a paused or
    idle one holds still, and the digits never change (legibility can't flicker)."""
    run = focus.Pomodoro(remaining=800, running=True)
    assert focus.render_body(run, beat=False) != focus.render_body(run, beat=True)
    paused = focus.Pomodoro(remaining=800, running=False)
    assert focus.render_body(paused, beat=False) == focus.render_body(paused, beat=True)
    assert focus.BRIGHT in focus.render_body(run, beat=True)   # digits still bright


def test_running_tile_breathes_on_beat():
    """D1: the minimized Focus tile gets a background wash on a beat while the
    timer runs, so the strip shows life at rest. Paused/idle never pulses."""
    run = focus.Pomodoro(remaining=700, running=True)
    assert focus.render_tile(run, beat=True) != focus.render_tile(run, beat=False)
    assert f"[on {focus.PULSE_BG}]" in focus.render_tile(run, beat=True)
    paused = focus.Pomodoro(remaining=700, running=False)
    assert focus.render_tile(paused, beat=True) == focus.render_tile(paused, beat=False)


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
