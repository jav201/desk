"""Focus panel — a pomodoro whose clock is a high-res braille dot-matrix, its
colour a thermometer that warms from cool to hot as the interval runs out.

Pure logic + Textual-markup renderers (no widgets), so it is trivially testable
and the app just drops the strings into its tiles/stage. State persists to
~/.desk/state.json so the timer survives a restart.
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

WORK_SECONDS = 25 * 60
POMO_SET = 5
POMO_MAX = 12
STATE_PATH = Path.home() / ".desk" / "state.json"

# Ember-field render palette: bright digits over a draining braille "bed" whose
# lit-dot mass tracks the remaining fraction. The bed carries the temperature
# gradient; the digits stay at full brightness so the time is always legible.
BRIGHT = "#dbe4ee"          # digit ink — never temperature-tinted
EMBER = "#8a5a4a"           # dim ash (drained skeleton, reserved)
DOT_DONE = "#ffd166"        # neutral set-progress ink (gold) — NOT temperature
DOT_NOW = "#2dd4bf"         # neutral set-progress ink (teal)
BED_COLS = 30               # braille columns of the ember field
BED_ROWS = 3                # 30*2*3*4 = 720 dots
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


def bed_lines(remaining_frac: float, cols: int = BED_COLS,
              rows: int = BED_ROWS, seed: int = BED_SEED,
              indent: int = 4) -> list[str]:
    """The ember field: `rows` braille lines whose lit-dot mass is proportional
    to `remaining_frac`. Dots evaporate in a fixed shuffled order (stable across
    ticks), and each cell is tinted by its horizontal position on the cool→hot
    ramp. Drained dots are blank, so the field visibly thins as time runs out.
    Every returned line has identical visible width (indent + cols)."""
    remaining_frac = max(0.0, min(1.0, remaining_frac))
    total = cols * 2 * rows * 4
    order = list(range(total))
    random.Random(seed).shuffle(order)
    lit = set(order[:round(remaining_frac * total)])
    pad = " " * indent
    out = []
    for cy in range(rows):
        chars = []
        for cx in range(cols):
            mask = 0
            for y in range(4):
                for x in range(2):
                    did = (cy * 4 + y) * (cols * 2) + (cx * 2 + x)
                    if did in lit:
                        mask |= _BIT[(x, y)]
            chars.append(chr(0x2800 + mask) if mask else " ")
        # coalesce runs of equal colour so the markup stays compact
        row, j = pad, 0
        while j < cols:
            hexv = temp_hex(j / (cols - 1)) if cols > 1 else temp_hex(0.5)
            k = j
            while k < cols and (temp_hex(k / (cols - 1)) if cols > 1 else temp_hex(0.5)) == hexv:
                k += 1
            row += f"[{hexv}]{''.join(chars[j:k])}[/]"
            j = k
        out.append(row)
    return out


# ---- pomodoro state ---------------------------------------------------------
@dataclass
class Pomodoro:
    remaining: int = WORK_SECONDS
    running: bool = False
    completed: int = 0                 # pomodoros finished in the current set
    target: int = POMO_SET             # size of the set (adjustable, 1..POMO_MAX)

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
                return True
        return False

    def toggle(self) -> None:
        if self.remaining == 0:
            self.remaining = WORK_SECONDS
        self.running = not self.running

    def skip(self) -> None:
        self.running = False
        self.completed = min(self.target, self.completed + 1)
        self.remaining = WORK_SECONDS

    def reset(self) -> None:
        self.running = False
        self.remaining = WORK_SECONDS
        self.completed = 0

    def add(self) -> None:
        self.target = min(POMO_MAX, self.target + 1)

    def remove(self) -> None:
        self.target = max(1, self.target - 1)
        if self.completed > self.target:
            self.completed = self.target


# ---- renderers (Textual markup strings) -------------------------------------
def render_tile(pomo: Pomodoro) -> str:
    hexv = temp_hex(pomo.elapsed_frac)
    mark = "▸" if pomo.running else "||"
    return f"[{hexv}]{mark} {mmss(pomo.remaining)}[/]  [dim]{dots(pomo.completed, pomo.target)}[/dim]"


def render_body(pomo: Pomodoro) -> str:
    """Ember-field layout: full-brightness braille digits over a draining bed of
    braille dots (mass ∝ remaining time), then neutral set-dots and controls."""
    state = "running" if pomo.running else ("done" if pomo.remaining == 0 else "paused")
    remaining_frac = pomo.remaining / WORK_SECONDS
    out = ["[bold #2dd4bf]FOCUS[/]", ""]
    for bl in braille_lines(mmss(pomo.remaining)):
        out.append(f"    [{BRIGHT}]{bl}[/]")
    out.append("")
    out.extend(bed_lines(remaining_frac))
    out.append("")
    out.append(dots_line(pomo.completed, pomo.target, state))
    out.append("")
    out.append("    [#ffd166]space[/] start/pause   [#ffd166]s[/] skip   [#ffd166]r[/] reset")
    out.append(f"    [#ffd166]+[/] / [#ffd166]-[/] pomodoros in the set  [dim]· now {pomo.target}[/dim]")
    return "\n".join(out)
