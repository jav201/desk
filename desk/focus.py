"""Focus panel — a pomodoro whose clock is a high-res braille dot-matrix, its
colour a thermometer that warms from cool to hot as the interval runs out.

Pure logic + Textual-markup renderers (no widgets), so it is trivially testable
and the app just drops the strings into its tiles/stage. State persists to
~/.desk/state.json so the timer survives a restart.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

WORK_SECONDS = 25 * 60
POMO_SET = 5
POMO_MAX = 12
STATE_PATH = Path.home() / ".desk" / "state.json"
JOURNAL_PATH = Path.home() / ".desk" / "pomodoros.jsonl"

# Ember-hearth render palette: bright digits carved out of a draining braille
# fire that fills the whole panel. The field carries the temperature gradient;
# the digits stay at full brightness so the time is always legible over it.
BRIGHT = "#dbe4ee"          # digit ink — never temperature-tinted
EMBER = "#8a5a4a"           # dim ash (drained skeleton, reserved)
DOT_DONE = "#ffd166"        # neutral set-progress ink (gold) — NOT temperature
DOT_NOW = "#2dd4bf"         # neutral set-progress ink (teal)
BED_SEED = 7                # fixed shuffle → dots evaporate in a stable order

# ---- braille clock font (6x8 dots, upscaled 2x, then 2x4-dot braille) -------
_DIG = {
    '0': [".####.", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."],
    '1': ["..##..", ".###..", "..##..", "..##..", "..##..", "..##..", "..##..", ".####."],
    '2': [".####.", "##..##", "....##", "...##.", "..##..", ".##...", "##....", "######"],
    '3': [".####.", "##..##", "....##", "..###.", "....##", "....##", "##..##", ".####."],
    '4': ["...###", "..####", ".##.##", "##..##", "######", "....##", "....##", "....##"],
    '5': ["######", "##....", "##....", "#####.", "....##", "....##", "##..##", ".####."],
    '6': [".####.", "##..##", "##....", "#####.", "##..##", "##..##", "##..##", ".####."],
    '7': ["######", "....##", "...##.", "..##..", "..##..", ".##...", ".##...", ".##..."],
    '8': [".####.", "##..##", "##..##", ".####.", "##..##", "##..##", "##..##", ".####."],
    '9': [".####.", "##..##", "##..##", "##..##", ".#####", "....##", "##..##", ".####."],
}
_COLON = ["..", "##", "##", "..", "..", "##", "##", ".."]
_BIT = {(0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (0, 3): 0x40,
        (1, 0): 0x08, (1, 1): 0x10, (1, 2): 0x20, (1, 3): 0x80}


def _upscale2(rows: list[str]) -> list[str]:
    out = []
    for r in rows:
        big = "".join(c * 2 for c in r)
        out.append(big)
        out.append(big)
    return out


def _braille_glyph(rows: list[str]) -> list[str]:
    R, C, out = len(rows), len(rows[0]), []
    for cy in range(R // 4):
        line = ""
        for cx in range(C // 2):
            mask = 0
            for y in range(4):
                for x in range(2):
                    if rows[cy * 4 + y][cx * 2 + x] == "#":
                        mask |= _BIT[(x, y)]
            line += chr(0x2800 + mask) if mask else " "
        out.append(line)
    return out


def braille_lines(timestr: str) -> list[str]:
    """The time as N equal-width braille rows (4 for the upscaled 6x8 font)."""
    glyphs = [_braille_glyph(_upscale2(_COLON if ch == ":" else _DIG[ch]))
              for ch in timestr]
    n = len(glyphs[0])
    return [" ".join(g[r] for g in glyphs) for r in range(n)]


# ---- temperature gradient (cool = fresh, hot = ending) ----------------------
# Stops as RGB triples; the last is repeated at 1.0 so interpolation has an
# upper anchor. temp_hex ramps smoothly between stops instead of snapping.
_TEMP = [(0.0, (0x45, 0xc4, 0xff)), (0.25, (0x34, 0xd1, 0xbf)),
         (0.5, (0xff, 0xd1, 0x66)), (0.72, (0xff, 0x8c, 0x42)),
         (0.9, (0xff, 0x3b, 0x30)), (1.0, (0xff, 0x3b, 0x30))]


def temp_hex(frac: float) -> str:
    """Smoothly interpolated cool→hot hex. Endpoints match the named stops
    (#45c4ff at 0.0, #ff3b30 at ≥0.9) so nothing snaps between bands."""
    frac = max(0.0, min(1.0, frac))
    for i in range(len(_TEMP) - 1):
        a, ca = _TEMP[i]
        b, cb = _TEMP[i + 1]
        if frac <= b:
            t = 0.0 if b == a else (frac - a) / (b - a)
            return "#%02x%02x%02x" % tuple(
                round(ca[k] + (cb[k] - ca[k]) * t) for k in range(3))
    return "#ff3b30"


def mmss(secs: int) -> str:
    m, s = divmod(max(0, secs), 60)
    return f"{m:02d}:{s:02d}"


def dots(done: int, total: int = POMO_SET) -> str:
    return "".join("●" if i < done else "○" for i in range(total))


def dots_line(completed: int, target: int, state: str) -> str:
    """Set-progress dots + caption, colour-coded by SET position only — done
    (gold ●), current (teal ◐), pending (dim ○). Never temperature-tinted, so
    the dots never cross-code with the ember field above them."""
    parts = []
    for i in range(target):
        if i < completed:
            parts.append(f"[{DOT_DONE}]●[/]")
        elif i == completed:
            parts.append(f"[{DOT_NOW}]◐[/]")
        else:
            parts.append("[dim]○[/dim]")
    cap = f"pomodoro {min(completed + 1, target)} of {target} · {state}"
    return f"    {''.join(parts)}  [dim]{cap}[/dim]"


def _lighten(hexv: str, factor: float) -> str:
    r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(min(255, round(v * factor)) for v in (r, g, b))


# ---- ember hearth (F1): the whole panel is a draining fire, clock carved in --
HEARTH_COLS = 30                                   # braille columns (60 dots)
HEARTH_ABOVE = 2                                   # field cell-rows above clock
HEARTH_BELOW = 3                                   # field cell-rows below clock
HEARTH_ROWS = HEARTH_ABOVE + 4 + HEARTH_BELOW      # 9 cell rows (clock is 4)
_HEARTH_BREATH = 1.16                              # per-beat brightness on the field
HEARTH_JIT = 2.6                                   # dot-rows of ragged on the front

# THE EMBER'S AMBIENT, declared rather than emergent.
#
# The breath lives in the GLYPH channel: `phase` rotates the front's raggedness,
# so the fire's edge moves while its mean height — the datum — does not. It used
# to live in the COLOUR channel alone (`_HEARTH_BREATH` lifting the fire's
# brightness on alternate ticks), and colour is the one channel that does not
# survive a monochrome terminal, a screenshot or a colour-blind reader. The
# colour lift is KEPT as a secondary touch, because it now carries nothing.
#
# An AMBIENT loops at >= 2000 ms; a TRANSITION lands in <= 400 ms; the span
# between is illegal, being too slow to read as a change and too fast to ignore.
# Four phases at the deck's one-second tick is a 4000 ms loop.
EMBER_PHASES = 4
EMBER_PERIOD_MS = 4000
EMBER_LEVEL = "basic"        # carries meaning -> survives TEXTUAL_ANIMATIONS=basic
# The ash above the front: dense smoke at the burn line, thinning with height.
# SEEDED-random rather than arithmetic — a periodic stipple like (x*5 + y*3) % 7
# paints a diagonal moiré that reads as corduroy and fights the carved digits.
_ASH_NEAR, _ASH_FAR, _ASH_FALLOFF = 0.34, 0.09, 6.0


def _flame_line(w_dots: int, h_dots: int, frac: float, phase: int = 0,
                seed: int = BED_SEED) -> list[float]:
    """The burn front: one dot-row height per dot-column.

    `base` is the datum and nothing else touches it. Each column carries its own
    independent random phase, so across 60 columns the jitter averages to within
    a tenth of a dot-row of the datum at every `phase` — rotating the phase
    changes the SHAPE of the line and not its MEAN, which is what keeps the
    breath a life channel instead of quietly editing the data channel.

    (The reference model paired alternate columns with an opposite sign and
    claimed that was what made the mean invariant. Measured over 24 phases it
    was WORSE — 0.38 dot-rows of spread against 0.17 — because the paired
    columns carry different random amplitudes and phases, so they never cancel.
    The averaging does the work; the pairing was decoration, and it is gone.)"""
    frac = max(0.0, min(1.0, frac))
    rng = random.Random(seed)
    amp = [rng.uniform(0.4, 1.0) * HEARTH_JIT for _ in range(w_dots)]
    ph = [rng.uniform(0.0, 2 * math.pi) for _ in range(w_dots)]
    base = (1.0 - frac) * h_dots
    return [base + amp[x] * math.sin(ph[x] + phase * 0.9)
            for x in range(w_dots)]


_ASH_CACHE: dict = {}


def _ash_grid(w_dots: int, h_dots: int) -> list[float]:
    """One seeded random value per dot, CACHED — the ash is texture, not noise:
    identical on every repaint, and costing a lookup per frame rather than a
    re-derivation, which is the one motion cost class that is actually dear."""
    key = (w_dots, h_dots)
    if key not in _ASH_CACHE:
        rng = random.Random(BED_SEED * 31 + w_dots)
        _ASH_CACHE[key] = [rng.random() for _ in range(w_dots * h_dots)]
    return _ASH_CACHE[key]


def _clock_dotrows(timestr: str) -> list[str]:
    """The mm:ss clock as 16 rows of a dot bitmap (the real 2x-upscaled font),
    so it can be carved into the ember field cell-for-cell."""
    glyphs = [_upscale2(_COLON if ch == ":" else _DIG[ch]) for ch in timestr]
    return ["..".join(g[y] for g in glyphs) for y in range(16)]


def hearth_lines(remaining_frac: float, timestr: str, beat: bool = False,
                 cols: int = HEARTH_COLS, seed: int = BED_SEED,
                 indent: int = 4, phase: int = 0) -> list[str]:
    """The whole Focus panel as one draining braille fire with the clock carved
    out of it.

    THE DATUM IS A BOUNDARY THAT MOVES. The burn front's HEIGHT is
    `remaining_frac`; below it solid fire, tinted by its horizontal cool→hot
    position; above it ash, a stipple that carries no datum and exists because
    the ground wants surface. The randomness is spent on the EDGE only.

    This replaces a shuffled per-dot drain. With 8 dots to a braille cell the
    odds of a cell going dark under a shuffle are (1-frac)**8, so the field
    painted 270 cells at 90 % and 268 at 50 % — the draining was invisible until
    the last minute. `record.py:_intake_field` already had the right answer in
    this same repo: a front that moves. Rows all share one width; digit cells
    carry ONLY digit dots, always at full BRIGHT, so the time never flickers."""
    remaining_frac = max(0.0, min(1.0, remaining_frac))
    W, H = cols * 2, HEARTH_ROWS * 4
    # carve the clock into the dot rows starting HEARTH_ABOVE cell-rows down
    art = _clock_dotrows(timestr)
    top = HEARTH_ABOVE * 4
    digit_dots = {(x, top + y) for y in range(16)
                  for x in range(min(W, len(art[y]))) if art[y][x] == "#"}
    digit_cells = {(x // 2, y // 4) for (x, y) in digit_dots}
    front = _flame_line(W, H, remaining_frac, phase, seed)
    ash = _ash_grid(W, H)
    pad = " " * indent
    out = []
    for cy in range(HEARTH_ROWS):
        cells = []                                 # (char, colour|None) per column
        for cx in range(cols):
            if (cx, cy) in digit_cells:
                mask = 0
                for y in range(4):
                    for x in range(2):
                        if (cx * 2 + x, cy * 4 + y) in digit_dots:
                            mask |= _BIT[(x, y)]
                cells.append((chr(0x2800 + mask), BRIGHT))
            else:
                fire = smoke = 0
                for y in range(4):
                    for x in range(2):
                        dx, dy = cx * 2 + x, cy * 4 + y
                        if dy >= front[dx]:
                            fire |= _BIT[(x, y)]
                        else:
                            up = front[dx] - dy
                            dens = (_ASH_FAR + (_ASH_NEAR - _ASH_FAR)
                                    * math.exp(-up / _ASH_FALLOFF))
                            if ash[dy * W + dx] < dens:
                                smoke |= _BIT[(x, y)]
                if fire:
                    col = temp_hex(cx / (cols - 1)) if cols > 1 else temp_hex(0.5)
                    cells.append((chr(0x2800 + fire),
                                  _lighten(col, _HEARTH_BREATH) if beat else col))
                elif smoke:
                    cells.append((chr(0x2800 + smoke), EMBER))
                else:
                    cells.append((" ", None))
        # coalesce equal-colour runs into compact markup; symmetric padding
        row, j = pad, 0
        while j < len(cells):
            col = cells[j][1]
            k = j
            while k < len(cells) and cells[k][1] == col:
                k += 1
            chunk = "".join(cells[i][0] for i in range(j, k))
            row += f"[{col}]{chunk}[/]" if col else chunk
            j = k
        out.append(row + pad)
    return out


# ---- the journal ------------------------------------------------------------
# state.json holds only the LIVE timer — remaining/running/completed/target, no
# timestamp of any kind — so yesterday has always been unrecoverable. This is
# the one file that fixes that: one JSON object per interval that ended, append
# only. It is what the day-close reads, and until it has lines the day-close has
# nothing true to say.
#
# It records DURATIONS AND OUTCOMES, never content: no note text, no path, no
# typed string. And it never raises — `Pomodoro.load` already sets that rule for
# this module, and a timer that dies because its log could not be written would
# be a worse bug than the missing log.
def append_journal(outcome: str, seconds: int, started_at: str | None = None,
                   path: Path | None = None) -> dict:
    """Append one interval to the journal and return the record written.

    Best-effort by design: a full disk, a read-only home or a stray directory
    where the file should be all end in a lost line and nothing else."""
    rec = {"started_at": started_at,
           "ended_at": datetime.now().isoformat(timespec="seconds"),
           "seconds": int(seconds),
           "outcome": outcome}
    path = path or JOURNAL_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    return rec


# ---- pomodoro state ---------------------------------------------------------
@dataclass
class Pomodoro:
    remaining: int = WORK_SECONDS
    running: bool = False
    completed: int = 0                 # pomodoros finished in the current set
    target: int = POMO_SET             # size of the set (adjustable, 1..POMO_MAX)

    # Wall-clock start of the interval now on the clock. Deliberately NOT a
    # dataclass field: `save()` is `asdict()`, so declaring it would change
    # state.json's shape for a value that is worthless across a restart. If the
    # app was restarted mid-interval it stays None and the journal says null,
    # which is the truth rather than a reconstructed guess.
    _started = None

    @classmethod
    def load(cls, path: Path | None = None) -> "Pomodoro":
        """Never raises: a missing/corrupt file yields a fresh timer."""
        path = path or STATE_PATH
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            target = max(1, min(POMO_MAX, int(d.get("target", POMO_SET))))
            return cls(
                remaining=max(0, min(WORK_SECONDS, int(d.get("remaining", WORK_SECONDS)))),
                running=bool(d.get("running", False)),
                completed=max(0, min(target, int(d.get("completed", 0)))),
                target=target,
            )
        except Exception:
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or STATE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self)), encoding="utf-8")

    @property
    def elapsed_frac(self) -> float:
        return 1.0 - self.remaining / WORK_SECONDS

    def tick(self) -> bool:
        """Advance one second if running. Returns True on the tick that completes
        the interval (so the caller can ring a bell)."""
        if self.running and self.remaining > 0:
            self.remaining -= 1
            if self.remaining == 0:
                self.running = False
                self.completed = min(self.target, self.completed + 1)
                append_journal("completed", WORK_SECONDS, self._started)
                self._started = None
                return True
        return False

    def toggle(self) -> None:
        if self.remaining == 0:
            self.remaining = WORK_SECONDS
        self.running = not self.running
        if self.running and self._started is None:
            self._started = datetime.now().isoformat(timespec="seconds")

    def skip(self) -> None:
        """Abandon the interval and count it. The journal keeps skips: a day
        with four skips and one completion is a fact about the day, and hiding
        it would make the close flatter."""
        self.running = False
        self.completed = min(self.target, self.completed + 1)
        append_journal("skipped", WORK_SECONDS - self.remaining, self._started)
        self._started = None
        self.remaining = WORK_SECONDS

    def reset(self) -> None:
        """Throw the set away. NOT journalled: reset means "this never counted",
        and it also zeroes `completed` — writing a line here would put work in
        the ledger that the user just declared didn't happen."""
        self.running = False
        self.remaining = WORK_SECONDS
        self.completed = 0
        self._started = None

    def add(self) -> None:
        self.target = min(POMO_MAX, self.target + 1)

    def remove(self) -> None:
        self.target = max(1, self.target - 1)
        if self.completed > self.target:
            self.completed = self.target


PULSE_BG = "#123a37"        # dark-teal wash: the running tile's heartbeat


# ---- renderers (Textual markup strings) -------------------------------------
def render_tile(pomo: Pomodoro, beat: bool = False) -> str:
    """The minimized strip tile. A RUNNING timer breathes: on a beat its time
    gets a faint dark-teal background wash, so the deck shows life at rest."""
    hexv = temp_hex(pomo.elapsed_frac)
    mark = "▸" if pomo.running else "||"
    time = f"[{hexv}]{mark} {mmss(pomo.remaining)}[/]"
    if pomo.running and beat:
        time = f"[on {PULSE_BG}]{time}[/]"
    return f"{time}  [dim]{dots(pomo.completed, pomo.target)}[/dim]"


def render_body(pomo: Pomodoro, beat: bool = False, phase: int = 0) -> str:
    """Ember-hearth layout: the whole panel is a draining braille fire with the
    clock carved out of it, then neutral set-dots and controls.

    A RUNNING timer breathes — the fire's edge moves through `phase`, and its
    brightness lifts on `beat` as a secondary touch. A paused or idle one holds
    completely still, which is a designed state and not an oversight: stillness
    is how the panel says the clock is not running."""
    state = "running" if pomo.running else ("done" if pomo.remaining == 0 else "paused")
    remaining_frac = pomo.remaining / WORK_SECONDS
    breathe = beat and pomo.running
    ph = (phase % EMBER_PHASES) if pomo.running else 0
    out = ["[bold #2dd4bf]FOCUS[/]", ""]
    out.extend(hearth_lines(remaining_frac, mmss(pomo.remaining),
                            beat=breathe, phase=ph))
    out.append("")
    out.append(dots_line(pomo.completed, pomo.target, state))
    out.append("")
    out.append("    [#ffd166]space[/] start/pause   [#ffd166]s[/] skip   [#ffd166]r[/] reset")
    out.append(f"    [#ffd166]+[/] / [#ffd166]-[/] pomodoros in the set  [dim]· now {pomo.target}[/dim]")
    return "\n".join(out)
