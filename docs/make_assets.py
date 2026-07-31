"""Regenerate everything in docs/ from the REAL app, headless.

Run: `python docs/make_assets.py`

WHY THIS FILE EXISTS. A screenshot is a claim about what the program does, and
it is the only claim in a README that nobody re-checks — the six images this
replaced were all captured before the deck existed and went on describing a
shell the code had stopped having. A generator makes the claim reproducible: if
an image and the code disagree, running this settles it in one command.

TWO RULES IT KEEPS.

1. EVERY PIXEL COMES OUT OF THE COMPOSITOR. The stills are Textual's own SVG
   export, and the animation is rasterised from `render_strips()` — the same
   styled cells the terminal is sent. Nothing here re-implements a renderer, so
   an image cannot show a layout the app cannot produce.

2. IT NEVER TOUCHES ~/.desk. Every path in the package that points at live user
   state is redirected to a temp directory BEFORE the app is imported. The
   autouse fixture in `tests/conftest.py` does this for the suite, but it only
   applies under pytest — a throwaway capture script is exactly how the
   operator's real pomodoro state gets overwritten, and it has happened.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

DOCS = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS.parent))

TMP = Path(tempfile.mkdtemp(prefix="desk-assets-"))

# ---- the fixture, installed before the app can read anything ----------------
from desk import board, capture, focus, record          # noqa: E402

focus.STATE_PATH = TMP / "state.json"
focus.JOURNAL_PATH = TMP / "pomodoros.jsonl"
focus.JOURNAL_ERROR = None
capture.CONFIG_PATH = TMP / "config.json"
capture.FALLBACK_PATH = TMP / "captures.md"
capture.DEFAULT_VAULT = TMP / "vault"
record.RECORD_SETTINGS_PATH = TMP / "record.json"
record.TRANSCRIPTS_DIR = TMP / "transcripts"
board.BOARD_PATH = TMP / "board.json"

assert focus.STATE_PATH.parent == TMP, "the fixture did not take"

TODAY = datetime.now()


def _iso(days: int, **kw) -> str:
    return (TODAY + timedelta(days=days)).strftime("%Y-%m-%d")


BOARD_FIXTURE = {
    "phases": ["Backlog", "Doing", "Done"],
    "projects": [
        {"id": "p1", "name": "Deck redesign", "color": "cyan"},
        {"id": "p2", "name": "Homelab MLOps", "color": "amber"},
        {"id": "p3", "name": "Telemetry lab", "color": "violet"},
        {"id": "p4", "name": "Course library", "color": "rose"},
    ],
    "tasks": [
        {"id": "t1", "title": "wire the geometry seat", "project_id": "p1",
         "phase": "Doing", "priority": "high", "due_date": _iso(2)},
        {"id": "t2", "title": "escape every untrusted string", "project_id": "p1",
         "phase": "Backlog", "priority": "high", "due_date": _iso(-1)},
        {"id": "t3", "title": "k3s on bare metal", "project_id": "p2",
         "phase": "Backlog", "priority": "normal", "due_date": _iso(5)},
        {"id": "t4", "title": "gamepad capture loop", "project_id": "p3",
         "phase": "Backlog", "priority": "normal", "due_date": _iso(9)},
        {"id": "t5", "title": "statistics track outline", "project_id": "p4",
         "phase": "Backlog", "priority": "low", "due_date": _iso(12)},
        {"id": "t6", "title": "ember boundary drain", "project_id": "p1",
         "phase": "Done"},
        {"id": "t7", "title": "day-close on real data", "project_id": "p1",
         "phase": "Done"},
        {"id": "t8", "title": "hue ration", "project_id": "p1", "phase": "Done"},
    ],
    "settings": {},
}
board.BOARD_PATH.write_text(json.dumps(BOARD_FIXTURE), encoding="utf-8")


def _journal() -> None:
    """A worked day, in the schema the WRITER actually writes.

    The first version of this invented `{at, kind, minutes}` from memory. Every
    field was wrong — the real record is `{started_at, ended_at, seconds,
    outcome}` — so `read_journal` discarded all ten lines, the close rendered
    its empty state, and the capture was one commit away from shipping a
    screenshot that said the feature does nothing. Hence the assertion at the
    bottom: a fixture that silently fails to take is worse than no fixture."""
    rows, t = [], TODAY.replace(hour=9, minute=12, second=0, microsecond=0)
    plan = [(25, "completed"), (5, "break"), (25, "completed"), (5, "break"),
            (25, "completed"), (11, "skipped"), (25, "completed"),
            (15, "break"), (25, "completed"), (18, "completed")]
    for mins, outcome in plan:
        started = t
        t += timedelta(minutes=mins)
        rows.append({"started_at": started.isoformat(timespec="seconds"),
                     "ended_at": t.isoformat(timespec="seconds"),
                     "seconds": mins * 60, "outcome": outcome})
        t += timedelta(minutes=3)
    focus.JOURNAL_PATH.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    from desk import close                      # the reader, not a re-implementation
    got = close.read_journal()
    assert len(got) == len(rows), (
        f"the journal fixture did not take: wrote {len(rows)} rows, "
        f"read_journal accepted {len(got)}")
    figures = close.stats(got)
    assert figures["completed"], f"no completed interval in the fixture: {figures}"
    print(f"journal fixture: {len(got)} rows, "
          f"{figures['completed']} completed, {figures.get('skipped', 0)} skipped")


_journal()

from desk.app import Deck                                # noqa: E402

# ---- capture ----------------------------------------------------------------
CELL_W, CELL_H = 12, 25
FONT_SIZE = 20


def _has_braille(font) -> bool:
    """Does this font actually DRAW braille, or is it drawing tofu?

    `font.getmask(ch).getbbox() is not None` says only that something was
    inked — and a missing-glyph box is something. Measured, DejaVu Sans Mono
    passed that check and rendered every braille codepoint as the identical
    52-pixel rectangle, blank U+2800 included, which would have shipped the
    ember as a field of boxes with no dot structure at all.

    The real question is whether the patterns DIFFER: an empty cell must draw
    nothing, a full cell must draw more than a half-full one. That is a
    property no substitution box can fake."""
    from PIL import Image, ImageDraw
    ink = []
    for ch in ("\u2800", "\u281b", "\u28ff"):        # blank, partial, full
        img = Image.new("L", (FONT_SIZE * 2, FONT_SIZE * 2), 0)
        ImageDraw.Draw(img).text((0, 0), ch, font=font, fill=255)
        ink.append(sum(1 for p in img.getdata() if p > 60))
    return ink[0] < 5 and ink[2] > ink[1] > 0


def _font():
    """A monospace font that really has braille. desk's hero is a braille
    field; capturing it with a font that lacks the block is not a worse
    screenshot, it is a different program."""
    from PIL import ImageFont
    import matplotlib
    mpl = Path(matplotlib.__file__).parent / "mpl-data/fonts/ttf"
    candidates = [Path(r"C:\Windows\Fonts\CascadiaMono.ttf"),
                  Path(r"C:\Windows\Fonts\CascadiaCode.ttf"),
                  Path("/usr/share/fonts/truetype/cascadia-code/CascadiaMono.ttf"),
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                  mpl / "DejaVuSans.ttf"]
    tried = []
    for p in candidates:
        if not p.exists():
            continue
        f = ImageFont.truetype(str(p), FONT_SIZE)
        if _has_braille(f):
            print(f"font: {p.name}")
            return f
        tried.append(p.name)
    raise SystemExit(
        "no font on this machine draws braille; the ember cannot be captured "
        f"honestly. Tried: {tried or 'none found'}. Install Cascadia Mono.")


def _rgb(colour, fallback):
    if colour is None:
        return fallback
    t = colour.get_truecolor()
    return (t.red, t.green, t.blue)


def raster(app, font):
    """One frame, painted cell by cell from the compositor's own styled output."""
    from PIL import Image, ImageDraw
    strips = list(app.screen._compositor.render_strips())
    w, h = app.size.width, len(strips)
    img = Image.new("RGB", (w * CELL_W, h * CELL_H), (13, 17, 23))
    draw = ImageDraw.Draw(img)
    for y, strip in enumerate(strips):
        x = 0
        for seg in strip:
            st = seg.style
            fg = _rgb(st.color if st else None, (201, 212, 224))
            bg = _rgb(st.bgcolor if st else None, (13, 17, 23))
            for ch in seg.text:
                if x >= w:
                    break
                px, py = x * CELL_W, y * CELL_H
                if bg != (13, 17, 23):
                    draw.rectangle([px, py, px + CELL_W - 1, py + CELL_H - 1], fill=bg)
                if ch.strip():
                    draw.text((px, py), ch, font=font, fill=fg)
                x += 1
    return img


async def shot(name: str, size, prep=None, title="desk") -> None:
    app = Deck()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        if prep:
            await prep(app, pilot)
            await pilot.pause()
        svg = app.export_screenshot(title=title)
    (DOCS / f"{name}.svg").write_text(svg, encoding="utf-8")
    print(f"  {name}.svg  {size[0]}x{size[1]}  {len(svg) // 1024} KB")


async def ember_gif(name: str = "ember") -> None:
    """The ember draining, and breathing while it drains.

    Both are real: `remaining` is stepped down the way a running interval steps
    it, and the phase advances on the same 1 s tick the app uses, so the ragged
    edge moves for the reason it moves in the product."""
    from PIL import Image                                # noqa: F401
    font, frames = _font(), []
    app = Deck()
    async with app.run_test(size=(72, 20)) as pilot:
        await pilot.pause()
        await pilot.press("f")
        app.pomo.running = True
        await pilot.pause()
        total, n = focus.WORK_SECONDS, 36
        for i in range(n):
            app.pomo.remaining = int(total * (1 - i / (n - 1)))
            app._ticks += 1                     # the ambient's phase, as it ticks
            _clock(app)                         # else the early frames read --:--:--
            app._paint()
            await pilot.pause()
            frames.append(raster(app, font))
    out = DOCS / f"{name}.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=130, loop=0, optimize=True)
    print(f"  {name}.gif  {len(frames)} frames  {out.stat().st_size // 1024} KB")


# ---- the shots --------------------------------------------------------------
async def _focus_running(app, pilot):
    _clock(app)
    app.pomo.running = True
    app.pomo.remaining = 754
    app.pomo.completed = 2
    app._ticks = 2
    await pilot.press("f")


def _clock(app) -> None:
    """The ribbon clock only fills on a tick, and a still that reads --:--:--
    looks like a bug rather than a screenshot taken before the first second."""
    app.clock = TODAY.strftime("%H:%M:%S")


async def _deck_running(app, pilot):
    app.pomo.running = True
    app.pomo.remaining = 754
    app.pomo.completed = 2
    app._ticks = 2
    _clock(app)
    app._paint()


async def _close(app, pilot):
    _clock(app)
    await pilot.press("d")


async def _record(app, pilot):
    _clock(app)
    await pilot.press("m")


async def main() -> None:
    print(f"fixture at {TMP}")
    print("stills:")
    await shot("deck-s", (40, 12), _deck_running, "desk — S · 40x12")
    await shot("deck-m", (80, 24), _deck_running, "desk — M · 80x24")
    await shot("deck-l", (120, 34), _deck_running, "desk — L · 120x34")
    await shot("focus", (80, 24), _focus_running, "desk — focus")
    await shot("close", (80, 26), _close, "desk — the day-close")
    await shot("record", (80, 24), _record, "desk — record")
    print("animation:")
    await ember_gif()
    home = Path.home() / ".desk"
    print(f"\n~/.desk touched: {(home / 'board.json').exists()} (must be False)")


if __name__ == "__main__":
    asyncio.run(main())
