"""Shell tests: the deck boots compact, expands/collapses each panel, and the
capture Input does NOT steal the panel hotkeys (the bug the prototype exposed)."""
from __future__ import annotations

from desk.app import Deck, PANELS


async def test_boots_compact():
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.mode == "strip"
        assert "hidden" in app.query_one("#stage").classes


async def test_expand_each_panel_then_collapse():
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        for key, name in (("b", "board"), ("f", "focus"), ("c", "capture")):
            await pilot.press(key)
            await pilot.pause()
            assert app.mode == name, (key, app.mode)
            assert "hidden" not in app.query_one("#stage").classes
            await pilot.press("escape")
            await pilot.pause()
            assert app.mode == "strip"


async def test_hotkeys_survive_the_capture_input():
    """WHY: a focusable Input in the tree silently swallows single-key hotkeys.
    If this regresses, `f` from rest would type into the box instead of opening
    Focus. Guarded by can_focus=False (off) + priority bindings."""
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")                      # must open Focus, not type 'f'
        await pilot.pause()
        assert app.mode == "focus"
        await pilot.press("c")                       # capture focuses the input
        await pilot.pause()
        inp = app.query_one("#cap-input")
        assert inp.display is True
        assert app.focused is inp


async def test_every_panel_has_a_placeholder_body():
    app = Deck()
    async with app.run_test() as pilot:
        await pilot.pause()
        for name in PANELS:
            app.action_expand(name)
            await pilot.pause()
            body = str(app.query_one("#stage-body").render())
            assert name.upper() in body.upper()
