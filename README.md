# desk

A frameless, always-on-top **widget deck** for the terminal — one window, a compact live strip that expands into panels on demand. Built with [Textual](https://textual.textualize.io/).

Panels:
- **Board** — your current *doing* task and a mini kanban, read live from the [taskboard](https://github.com/jav201/taskboard) app.
- **Focus** — a pomodoro whose clock is a high-res braille dot-matrix, coloured by a cool→hot thermometer of elapsed time.
- **Capture** — a rotating prompt; press enter and the line lands in your Obsidian daily note (or a local file when the vault isn't around).

## Install

`desk` and `taskboard` are two independent tools. `desk` reads taskboard's data file but does **not** depend on its code — so install taskboard too if you want the Board panel populated with your tasks.

```bash
# 1. the widget deck
git clone https://github.com/jav201/desk
cd desk
pip install -e .

# 2. taskboard — so the Board panel has data to show
git clone https://github.com/jav201/taskboard
cd taskboard
pip install -e .
```

Prefer isolated installs? Use `pipx install <path>` in each folder, or `pip install git+https://github.com/jav201/desk`.

Run it:

```bash
desk
```

## Keys

| key | action |
|-----|--------|
| `b` | Board panel |
| `f` | Focus panel |
| `c` | Capture panel |
| `esc` | collapse to the strip |
| `space` | pomodoro start / pause |
| `s` | pomodoro skip |
| `r` | pomodoro reset |
| `F5` | refresh the board now |
| `q` | quit |

## Data & config

- **Board** reads `~/.taskboard/board.json` (written by taskboard) read-only, auto-refreshing every ~5s; `F5` forces an instant reload. No taskboard installed? The Board panel simply shows "no board loaded".
- **Focus** persists the pomodoro to `~/.desk/state.json`, so the timer survives a restart.
- **Capture** appends `- YYYY-MM-DD HH:MM  <text>` under a `## Captures` heading in `<vault>/Daily/YYYY-MM-DD.md`. Point it at your vault in `~/.desk/config.json`:

  ```json
  { "vault": "G:/path/to/your/Obsidian/Vault", "daily_subdir": "Daily" }
  ```

  If the vault folder isn't reachable (e.g. a different computer), captures fall back to a single local file `~/.desk/captures.md`, grouped by day — nothing is lost.

## Frameless, always-on-top (desktop-widget mode)

Textual can't remove the OS window chrome — the terminal does. Use [WezTerm](https://wezterm.org):

1. Copy the bundled `wezterm.lua` to `~/.wezterm.lua` (WezTerm loads it automatically), or point WezTerm at it with `--config-file`.
2. Run `desk` in that window; it opens borderless.
3. Pin it always-on-top with [PowerToys → Always On Top](https://learn.microsoft.com/windows/powertoys/) (`Win+Ctrl+T`).

`Ctrl+Shift+B` toggles the frame back on; `F11` is borderless fullscreen. (Windows Terminal / PowerShell can't go borderless — that's why WezTerm.)

## Adding a widget (for later)

The deck is built to grow. Each panel is a small module (`desk/board.py`, `desk/focus.py`, `desk/capture.py`) exposing `render_tile(...)` and `render_body(...)`. To add a new widget:

1. Write `desk/<name>.py` with those two renderers (plus any state it needs).
2. In `desk/app.py`: add it to `PANELS`, add a tile entry in `_tiles`, a branch in `_body`, and a hotkey `Binding`.

Panels are deliberately decoupled — data flows through files, not cross-imports — so a new widget slots in without touching the others. A panel registry is the natural refactor once there are more than a handful.

## Development

```bash
pip install -e ".[test]"
pytest -q
```
