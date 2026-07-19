"""Focus panel — a pomodoro whose clock is a high-res braille dot-matrix, its
colour a thermometer that warms from cool to hot as the interval runs out.

Pure logic + Textual-markup renderers (no widgets), so it is trivially testable
and the app just drops the strings into its tiles/stage. State persists to
~/.desk/state.json so the timer survives a restart.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

WORK_SECONDS = 25 * 60
POMO_SET = 5
STATE_PATH = Path.home() / ".desk" / "state.json"

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
_TEMP = [(0.0, "#45c4ff"), (0.25, "#34d1bf"), (0.5, "#ffd166"),
         (0.72, "#ff8c42"), (0.9, "#ff3b30")]


def temp_hex(frac: float) -> str:
    hexv = _TEMP[0][1]
    for thr, h in _TEMP:
        if frac >= thr:
            hexv = h
    return hexv


def mmss(secs: int) -> str:
    m, s = divmod(max(0, secs), 60)
    return f"{m:02d}:{s:02d}"


def dots(done: int, total: int = POMO_SET) -> str:
    return "".join("●" if i < done else "○" for i in range(total))


# ---- pomodoro state ---------------------------------------------------------
@dataclass
class Pomodoro:
    remaining: int = WORK_SECONDS
    running: bool = False
    completed: int = 0                 # pomodoros finished in the current set

    @classmethod
    def load(cls, path: Path | None = None) -> "Pomodoro":
        """Never raises: a missing/corrupt file yields a fresh timer."""
        path = path or STATE_PATH
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                remaining=max(0, min(WORK_SECONDS, int(d.get("remaining", WORK_SECONDS)))),
                running=bool(d.get("running", False)),
                completed=max(0, min(POMO_SET, int(d.get("completed", 0)))),
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
                self.completed = min(POMO_SET, self.completed + 1)
                return True
        return False

    def toggle(self) -> None:
        if self.remaining == 0:
            self.remaining = WORK_SECONDS
        self.running = not self.running

    def skip(self) -> None:
        self.running = False
        self.completed = min(POMO_SET, self.completed + 1)
        self.remaining = WORK_SECONDS

    def reset(self) -> None:
        self.running = False
        self.remaining = WORK_SECONDS
        self.completed = 0


# ---- renderers (Textual markup strings) -------------------------------------
def render_tile(pomo: Pomodoro) -> str:
    hexv = temp_hex(pomo.elapsed_frac)
    mark = "▸" if pomo.running else "||"
    return f"[{hexv}]{mark} {mmss(pomo.remaining)}[/]  [dim]{dots(pomo.completed)}[/dim]"


def _thermometer(frac: float, width: int = 24) -> tuple[str, str]:
    cells = "".join(f"[{temp_hex(i / (width - 1))}]█[/]" for i in range(width))
    marker = round(frac * (width - 1))
    mrow = " " * marker + "▲" + " " * (width - 1 - marker)
    return cells, mrow


def render_body(pomo: Pomodoro) -> str:
    hexv = temp_hex(pomo.elapsed_frac)
    state = "running" if pomo.running else ("done" if pomo.remaining == 0 else "paused")
    cells, mrow = _thermometer(pomo.elapsed_frac)
    out = ["[bold #2dd4bf]FOCUS[/]", ""]
    for bl in braille_lines(mmss(pomo.remaining)):
        out.append(f"    [{hexv}]{bl}[/]")
    out.append("")
    out.append(f"    [dim]cool[/dim] {cells} [dim]hot[/dim]")
    out.append(f"         {mrow}")
    out.append(f"    [{hexv}]{dots(pomo.completed)}[/]  "
               f"[dim]pomodoro {min(pomo.completed + 1, POMO_SET)} of {POMO_SET} · {state}[/dim]")
    out.append("")
    out.append("    [#ffd166]space[/] start/pause    [#ffd166]s[/] skip    [#ffd166]r[/] reset")
    return "\n".join(out)
