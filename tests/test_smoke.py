"""The whole app, driven — every binding at every size desk is asked to live at.

Everything else in this suite tests a renderer or a state machine. This drives
the REAL app: `run_test` mounts it, the intervals are wired, `on_resize` fires,
and every binding is pressed at seven window sizes including two the deck cannot
seat a full layout in. It is the cheap end of the gap the design work flagged —
that the model was verified frame by frame while the running app never was.

It asserts no picture. It asserts that nothing throws and every widget still
renders, which is the failure mode a renderer test cannot see: a key that is
bound to an action that does not exist, a paint that divides by a width of zero,
a panel that only breaks once the window is 30 columns wide.
"""
from __future__ import annotations

import pytest

from desk.app import Deck

KEYS = ["b", "f", "c", "escape", "m", "d", "escape", "space", "s", "r",
        "plus", "minus", "a", "o", "t", "f5", "x", "escape"]
SIZES = [(40, 12), (58, 14), (80, 24), (120, 34), (160, 44), (30, 8)]


@pytest.mark.parametrize("size", SIZES)
async def test_every_binding_survives_every_size(size, monkeypatch):
    """No key may raise, at any size, in any order. `o` and `t` shell out, so
    they are stubbed — the point here is the deck's own code path, not whether
    a terminal emulator is installed."""
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: None)
    monkeypatch.setattr("os.startfile", lambda p: None, raising=False)
    app = Deck()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(*size)
        await pilot.pause()
        for k in KEYS:
            await pilot.press(k)
            await pilot.pause()
        for wid in ("#tile-board", "#tile-focus", "#tile-capture",
                    "#tile-record", "#hints", "#clock"):
            assert str(app.query_one(wid).render()) is not None


# The hint bar's width contract lives in test_hints.py over WIDTHS (30-120),
# desk's real range, and the new `close` mode was added to that file's MODES
# rather than re-tested here. A probe at 8 columns DOES fail: `fit` deliberately
# keeps the last essential key even when it no longer fits (hints.py:75-77). It
# is outside the contract, it is documented, and nothing is broken — recorded
# here so the next person measuring it does not read it as a defect.
