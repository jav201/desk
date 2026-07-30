"""The hue ration — project hues NAME, severity hues JUDGE, no mark wears both.

A project hue answers "whose is this?"; a severity hue answers "how bad is
this?". They are different questions, and a colour that answers both answers
neither. desk obeyed this without writing it down, and the one place it had
drifted was measurable: `orange` (#fb923c, taskboard's project palette) sat NINE
rgb units from the high-priority chip (#ff8c42), so a task in an orange project
was painted the same colour as an urgency flag, on the same row.

The resolution is not to retune the orange. Severity has four houses — a
reserved hue, brightness, glyph/position, and the field — and hue is capped at
ONE of them. Overdue keeps it, because a date that has passed is the only thing
desk is willing to judge. High priority moves to the GLYPH house it already
lived in: `!2` is a mark and a count, and the colour was always redundant.
"""
from __future__ import annotations

import json
import math

from desk import board, focus


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _dist(a, b):
    return math.dist(_rgb(a), _rgb(b))


RESERVED = {"overdue": board._OVER}


def test_severity_spends_exactly_one_hue():
    """The cap is the whole mechanism. A second reserved hue does not add a
    second signal — it dilutes the first, because the eye stops reading "a
    colour like that means trouble" and starts reading "some colours mean
    something". #ff8c42 was that second hue and it is gone."""
    assert len(RESERVED) == 1
    assert not hasattr(board, "_HIGH"), "a second severity hue came back"


def test_no_project_hue_can_be_mistaken_for_the_reserved_one():
    """A project bar that reads as an alert is a false alarm every time the
    board is drawn. The closest today is `rose` at 64 rgb units."""
    near = {n: round(_dist(h, board._OVER), 1)
            for n, h in board._COLOR_HEX.items()
            if _dist(h, board._OVER) < 40}
    assert not near, f"project hues too close to the overdue hue: {near}"


def test_high_priority_is_a_glyph_and_a_count(tmp_path):
    """THE POSITIVE HALF. Dropping the hue is only correct if the signal
    survives without it — otherwise this is deletion, not a ration. The chip
    must still be on the row, still say how many, and still not be red."""
    data = {"projects": [{"id": "p1", "name": "Web", "color": "orange"}],
            "tasks": [{"id": "a", "title": "one", "project_id": "p1",
                       "status": "backlog", "priority": "high"},
                      {"id": "b", "title": "two", "project_id": "p1",
                       "status": "backlog", "priority": "high"}],
            "settings": {}}
    p = tmp_path / "board.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    body = board.render_body(board.load(p))
    assert "!2" in body                                  # the mark and the count
    line = next(l for l in body.splitlines() if "!2" in l)
    assert board._OVER not in line.split("!2")[0][-30:], line


# The seats allowed to tint with the temperature ramp, declared as data so the
# law has an oracle that is not the renderer.
RAMP_SEATS = {"hearth_lines", "render_tile"}


def test_only_the_declared_seats_tint_with_the_fire(monkeypatch):
    """MEASURED AS PROVENANCE, because colour identity cannot answer the
    question. A gold set-dot and a gold flame cell are the same six characters,
    so a test that scans the output for ramp hexes reports a collision that
    isn't one (the first draft of this test did exactly that, and was wrong).
    What matters is WHO tinted: the ramp belongs to the fire's horizontal axis
    and to the strip tile's own clock, and to nothing that describes a TASK."""
    seen = set()
    real = focus.temp_hex

    def spy(frac):
        import inspect
        seen.add(inspect.stack()[1].function)
        return real(frac)

    monkeypatch.setattr(focus, "temp_hex", spy)
    pomo = focus.Pomodoro(remaining=700, running=True)
    focus.render_body(pomo)
    focus.render_tile(pomo)
    focus.dots_line(completed=2, target=5, state="running")
    assert seen <= RAMP_SEATS, f"the fire's ramp leaked into: {seen - RAMP_SEATS}"
    assert seen, "the spy never fired — the law is measuring nothing"


def test_the_set_dots_are_deaf_to_the_temperature():
    """The other half, stated as behaviour rather than provenance: the set-dots
    line is coded by SET POSITION only, so it renders identically at 25:00 and
    at 00:30. desk says this in a comment at focus.py:112; here it is a law."""
    def dots_row(rem):
        body = focus.render_body(focus.Pomodoro(remaining=rem, completed=2))
        return next(l for l in body.splitlines() if "○" in l or "◐" in l)
    assert dots_row(focus.WORK_SECONDS) == dots_row(30)


def test_gold_is_shared_with_the_fire_on_purpose():
    """THE DECLARED EXCEPTION, kept honest by being asserted rather than
    tolerated. desk's gold is the ATTENTION hue, not a severity hue, and the
    fire's 0.5 stop is the same gold. A shared warm anchor between the fire and
    the "now" mark is part of why the app reads as one world. If that ever stops
    being deliberate, this test is where it gets argued, not discovered."""
    assert focus.temp_hex(0.5) == board._GOLD == "#ffd166"


def _hexes(markup: str):
    import re
    return re.findall(r"#[0-9a-fA-F]{6}", markup)
