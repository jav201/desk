"""The day-close — and above all, that it never invents a figure.

The close is the one screen in desk whose whole value is that its numbers are
true. `state.json` carries no timestamp, so every figure here would have been
fiction before the journal existed; the tests that matter most are therefore the
ones asserting the empty day stays empty.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from desk import close, focus
from desk.app import Deck

TODAY = date(2026, 7, 30)


def _strip(m: str) -> str:
    return re.sub(r"\[/?[^\]]*\]", "", m)


def _rec(hour, minute=0, outcome="completed", seconds=1500, day=TODAY):
    return {"started_at": None,
            "ended_at": datetime(day.year, day.month, day.day, hour,
                                 minute).isoformat(timespec="seconds"),
            "seconds": seconds, "outcome": outcome}


def _write(path, recs):
    path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")


# ---- the honesty laws -------------------------------------------------------
def test_an_empty_day_prints_no_number():
    """THE LAW THIS SCREEN EXISTS UNDER. A close that renders zeroes for a day
    with no entries is not reporting an empty day — it is reporting a result of
    nothing, which is a different and false claim. The empty state says the
    journal opens today and shows no figure at all."""
    body = _strip(close.render_body([], TODAY))
    assert "the journal opens today" in body
    assert not re.search(r"\d+\s+(minutes|completed|skipped)", body), body
    assert "hot hour" not in body


def test_every_figure_comes_from_the_journal():
    """Two records, and each number on the screen is traceable to them."""
    recs = [_rec(9, outcome="completed", seconds=1500),
            _rec(9, minute=30, outcome="completed", seconds=1500),
            _rec(14, outcome="skipped", seconds=300)]
    parsed = [dict(r, _ended=datetime.fromisoformat(r["ended_at"])) for r in recs]
    body = _strip(close.render_body(parsed, TODAY))
    assert "55 minutes" in body                 # 25 + 25 + 5
    assert "2 completed" in body
    assert "1 skipped" in body
    assert "09:00 was the hot hour" in body     # 50 min beats 14:00's 5
    assert "14:00" in body                      # and the thinnest is named


def test_a_corrupt_line_costs_that_line_and_nothing_else(tmp_path):
    """A half-written record must not take the screen down with it — the file is
    appended to by a running app and can be read mid-write."""
    p = tmp_path / "j.jsonl"
    p.write_text(json.dumps(_rec(10)) + "\n"
                 + '{"ended_at": "not-a-date"}\n'
                 + "{ broken\n"
                 + json.dumps(_rec(11)) + "\n", encoding="utf-8")
    rows = close.read_journal(p)
    assert len(rows) == 2
    assert close.stats(rows, TODAY)["intervals"] == 2


def test_a_missing_journal_is_an_empty_day_not_an_error(tmp_path):
    assert close.read_journal(tmp_path / "nope.jsonl") == []


# ---- the hero ---------------------------------------------------------------
def test_the_hour_band_is_a_boundary_not_a_scatter():
    """The hero has to distinguish a 40-minute hour from a 20-minute one, or the
    shape of the day is not on the screen. Filled from the floor up, so the
    height IS the reading."""
    def lit(minutes):
        """Dots painted as FIRE, not dots painted at all — the unlit track
        carries ink too, so counting every dot reports a constant (the first
        draft of this oracle did exactly that and read 112/104/104)."""
        band = close.hour_band([minutes] + [0.0] * 23)
        n = 0
        for row in band:
            for m in re.finditer(rf"\[{re.escape(close.GOLD)}\]([^\[]*)", row):
                n += sum(bin(ord(c) - 0x2800).count("1")
                         for c in m.group(1) if c != " ")
        return n
    a, b, c = lit(60), lit(30), lit(5)
    assert a > b > c > 0, (a, b, c)
    assert a / c >= 3.0, (a, b, c)


def test_the_band_is_a_full_field_even_on_a_thin_day():
    """The unlit track is drawn. Without it a quiet day is three marks floating
    on black, which reads as a broken widget rather than as a quiet day."""
    band = close.hour_band([0.0] * 24)
    assert all(close.ASH in r for r in band), "the empty band has no track"
    ink = sum(1 for r in band for ch in _strip(r) if ch != " ")
    assert ink > 24 * close.HOUR_CELLS, ink


def test_the_unlit_track_is_a_LATTICE_and_not_a_WALL():
    """THE DEFECT THIS SCREEN SHIPPED IN ITS FIRST BUILD, and the reason a test
    count is not a design review. Unlit cells were drawn as a FULL braille block
    in ash and lit ones as a full block in gold — the same glyph, differing only
    in colour. In greyscale the hero was one solid rectangle and the day had no
    shape at all. It was found by rendering the frame and looking at it.

    The rule the fix encodes: the unlit track carries ink, and at most a quarter
    of the cell. Nothing that is not the datum may read as mass."""
    empty = _strip(close.hour_band([0.0] * 24)[0]).strip()
    glyphs = {ord(c) - 0x2800 for c in empty if c != " "}
    assert glyphs, "the track vanished"
    assert max(bin(g).count("1") for g in glyphs) <= 2, (
        f"the unlit track fills {max(bin(g).count('1') for g in glyphs)}/8 dots "
        "— that is a wall, not a lattice")


def test_the_days_shape_survives_with_the_colour_stripped():
    """The datum lives in the GLYPH, not in the hue. Measured as lit mass with
    all markup removed, because that is what a colour-blind reader, a monochrome
    terminal and a screenshot all see. The wall passed a mere
    are-the-strings-different check; it cannot pass this one."""
    def mass(by_hour):
        return sum(bin(ord(c) - 0x2800).count("1")
                   for r in close.hour_band(by_hour)
                   for c in _strip(r) if c != " ")
    calm = mass([0.0] * 24)
    typical = mass([0.0] * 9 + [50.0, 25.0, 0, 0, 40.0] + [0.0] * 10)
    extreme = mass([55.0] * 24)
    assert calm < typical < extreme, (calm, typical, extreme)
    assert extreme > calm * 4, (calm, extreme)


def test_the_band_has_one_row_length():
    band = close.hour_band([30.0] * 24)
    assert len({len(_strip(r)) for r in band}) == 1
    assert len(band) == close.BAND_ROWS


def test_the_three_states_look_different():
    """calm / typical / extreme, and no two alike — a screen whose states render
    the same has a dead channel."""
    calm = [0.0] * 24
    typical = [0.0] * 9 + [50.0, 25.0, 0.0, 0.0, 40.0] + [0.0] * 10
    extreme = [55.0] * 24
    keys = {_strip("\n".join(close.hour_band(b)))
            for b in (calm, typical, extreme)}
    assert len(keys) == 3


# ---- the streak -------------------------------------------------------------
def test_the_streak_does_not_break_just_because_today_is_young():
    """Opening the close at 09:00 with nothing done yet must not report a run of
    three as zero. A streak is a fact about days that are over."""
    days = [TODAY - timedelta(days=n) for n in (1, 2, 3)]
    rows = [dict(_rec(10, day=d), _ended=datetime(d.year, d.month, d.day, 10))
            for d in days]
    assert close.stats(rows, TODAY)["streak"] == 3


def test_a_skipped_day_ends_the_streak():
    """THE CONTROL: a streak that never breaks is a counter, not a streak."""
    days = [TODAY - timedelta(days=n) for n in (1, 3, 4)]      # day 2 missing
    rows = [dict(_rec(10, day=d), _ended=datetime(d.year, d.month, d.day, 10))
            for d in days]
    assert close.stats(rows, TODAY)["streak"] == 1


def test_only_completions_build_a_streak():
    d = TODAY - timedelta(days=1)
    rows = [dict(_rec(10, outcome="skipped", day=d),
                 _ended=datetime(d.year, d.month, d.day, 10))]
    assert close.stats(rows, TODAY)["streak"] == 0


# ---- the app seat -----------------------------------------------------------
async def test_d_opens_the_close_and_esc_leaves_it(tmp_path):
    """The key is bound, the screen renders through the real app, and the way
    out works — the close is a place you can get out of."""
    _write(focus.JOURNAL_PATH, [_rec(9, day=date.today())])
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert app.mode == "close"
        body = _strip(str(app.query_one("#stage-body").render()))
        assert "CLOSE" in body and "1 completed" in body
        await pilot.press("escape")
        await pilot.pause()
        assert app.mode == "strip"


async def test_the_close_reads_the_journal_the_app_itself_wrote(tmp_path):
    """END TO END, and the point of increment 1: an interval completed inside
    the running app is counted by the close. Nothing in between is stubbed."""
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        app.pomo.remaining = 1
        app._tick()
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        body = _strip(str(app.query_one("#stage-body").render()))
        assert "1 completed" in body, body
        assert "25 minutes" in body, body
