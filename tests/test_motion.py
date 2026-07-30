"""desk's motion — which channel it moves in, and at what rate.

Two rules decide whether a moving surface is alive or merely busy:

  1. A motion is either a TRANSITION (<= 400 ms, one shot) or an AMBIENT
     (>= 2000 ms, looping). The span between is illegal: too slow to read as a
     change, too fast to stop noticing.
  2. The channels are GLYPH and CELL POSITION. Colour is not one — it is the
     channel that does not survive a monochrome terminal, a screenshot, or a
     reader who cannot separate the hues.

desk's ember used to breathe by brightening the fire on alternate ticks, which
is rule 2 broken. The breath now rotates the burn front's raggedness instead.
"""
from __future__ import annotations

import re

from desk import focus
from desk.app import Deck

ILLEGAL = (400, 2000)          # nothing may have a period in here


def _strip(m: str) -> str:
    return re.sub(r"\[/?[^\]]*\]", "", m)


def test_the_embers_period_is_in_a_legal_regime():
    assert not (ILLEGAL[0] < focus.EMBER_PERIOD_MS < ILLEGAL[1]), (
        f"{focus.EMBER_PERIOD_MS} ms sits in the illegal gap")
    assert focus.EMBER_PERIOD_MS >= ILLEGAL[1], "an ambient must loop slowly"


def test_the_declared_period_is_what_the_app_actually_runs():
    """A declared period that the code does not produce is a comment, not a
    contract. The deck ticks once a second and advances one phase per tick, so
    the loop is EMBER_PHASES seconds — asserted against both ends."""
    assert focus.EMBER_PERIOD_MS == focus.EMBER_PHASES * 1000
    import inspect
    from desk import app as app_mod
    on_mount = inspect.getsource(app_mod.Deck.on_mount)
    assert "set_interval(1.0, self._tick)" in on_mount, on_mount


def test_the_ambient_carries_meaning_so_it_survives_reduced_animation():
    """`basic` is the level that keeps running when a user asks for less
    motion. The ember qualifies because its movement is the fire's edge — take
    it away and the panel stops saying the timer is running at all."""
    assert focus.EMBER_LEVEL == "basic"


def test_the_breath_moves_the_GLYPH_not_only_the_COLOUR():
    """The law the old implementation broke. Compared with all markup stripped,
    so a change that lives purely in a hex value is invisible here — which is
    exactly what it would be to a reader in monochrome."""
    run = focus.Pomodoro(remaining=700, running=True)
    frames = {_strip(focus.render_body(run, phase=p))
              for p in range(focus.EMBER_PHASES)}
    assert len(frames) == focus.EMBER_PHASES, (
        "the ambient does not move in the glyph channel")


def test_a_stopped_timer_holds_completely_still():
    """Stillness is a DESIGNED state here, not a missing feature: a paused panel
    that keeps breathing is telling the user the clock is running."""
    paused = focus.Pomodoro(remaining=700, running=False)
    frames = {focus.render_body(paused, phase=p)
              for p in range(focus.EMBER_PHASES)}
    assert len(frames) == 1


def test_the_counter_never_moves_while_the_fire_does():
    """The one thing on the panel that must be trusted at a glance."""
    run = focus.Pomodoro(remaining=754, running=True)
    digits = set()
    for p in range(focus.EMBER_PHASES):
        body = focus.render_body(run, phase=p)
        digits.add(tuple(m.group(1) for m in
                         re.finditer(rf"\[{re.escape(focus.BRIGHT)}\]([^\[]*)",
                                     body)))
    assert len(digits) == 1


async def test_the_running_deck_actually_breathes(tmp_path):
    """THE SEAT THAT MATTERS: through the real app's own interval, not by
    calling the renderer with hand-picked phases. A phase that is computed
    correctly and never passed is a still panel with a passing unit test.

    THE CLOCK IS PINNED, and that is the whole trick. The first version of this
    test just ticked four times and counted distinct frames — which passed even
    with `phase=0` hard-wired, because the carved counter reads 24:59, 24:58,
    24:57 and the frames differ for a reason that has nothing to do with the
    ambient. Holding `remaining` fixed leaves the phase as the only thing that
    can move, so the count means what it says."""
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.press("space")
        await pilot.pause()
        seen = set()
        for _ in range(focus.EMBER_PHASES):
            app.pomo.remaining = 701          # pinned: the tick makes it 700
            app._tick()
            await pilot.pause()
            assert app.pomo.remaining == 700, "the clock moved — control broken"
            seen.add(_strip(str(app.query_one("#stage-body").render())))
        assert len(seen) == focus.EMBER_PHASES, (
            f"{len(seen)} distinct frames over a full loop with the clock "
            "pinned — the ambient is not reaching the screen")
