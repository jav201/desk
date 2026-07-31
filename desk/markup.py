"""One escape, for every string desk did not write itself.

THE TWO-PARSER TRAP, measured. Every module here used to reach for
`rich.markup.escape`, which is the obvious choice and the wrong one, because
desk does not render through rich's parser — a `Static.update(...)` goes through
Textual's. The two do not agree on what a tag is:

    rich   escapes `[` only when the next character is a-z, `#`, `/` or `@`
           (its regex is `\\[[a-z#/@][^[]*?]`)
    textual opens a tag on ANY `[` not preceded by a backslash, and accepts
           `[@a-zA-Z_-][a-zA-Z0-9_-]*=` plus `$variable` references

So an uppercase, underscored or `$`-prefixed tag walks straight through rich's
escape and is then parsed by Textual. Measured on textual 8.2.8, wrapped in
desk's own `[dim]…[/dim]`:

    rich escape            textual result
    [@click=app.quit]…     inert
    [Bold]X[/]             LIVE SPAN, style "Bold"
    [_x]y[/]               LIVE SPAN, style "_x"
    [$accent]X[/]          LIVE SPAN, painted the app's real accent

A web video's title is fetched over the network and a filename comes off a
disk this app does not own, so both are strings an attacker can choose. The
consequences were not cosmetic: `[@click=app.pwned]` dispatches into desk's own
action namespace on click, and a title of `[/]` raises out of the compositor and
crashes the deck on every repaint — a one-character permanent denial of service.

Escaping the bracket itself is what closes it, because the bracket is what both
parsers agree opens a tag. It is also strictly more faithful than rich's escape,
which corrupts `[[double]]` and double-escapes an already-escaped bracket.

THE ONE LOSS, declared. Textual's lookbehind is a single character — `(?<!\\)\\[`
— so it cannot count backslashes, and no amount of doubling saves a string that
ENDS in one: the caller's own closing tag is the thing that gets escaped, and the
tag leaks into the text as `[/dim]`. Trailing backslashes are therefore dropped.
A rendered title loses a final `\\`; the alternative was showing desk's own
markup to the reader.
"""
from __future__ import annotations

__all__ = ["esc"]


def esc(text) -> str:
    """`text`, rendered as literal characters by Textual's markup parser."""
    return str(text).replace("[", "\\[").rstrip("\\")
