"""desk's register — the app has no opinion about you.

This is a design law, not a style preference, and it is the one question a
surface that MEASURES YOUR BEHAVIOUR cannot avoid answering: how does it speak
on the day you failed? desk's answer is that it states facts about the world and
never about the reader. "nothing in progress", not "you have nothing in
progress". The fire goes out and leaves ash — brown and quiet — and the only red
on the surface is worn by a DATE that has passed, never by the person who let it
pass.

desk therefore has TWO voices, and the distinction is the whole rule:

  - the APP's voice — no second person, lowercase, factual;
  - the QUOTED voice — capture.py's prompts, which do address the reader,
    because there the app is not speaking: it is holding up the user's own
    question. They are also the only Title Case strings in the product, which is
    the typographic signal that someone else is talking.

Enforced by reading the source rather than by intention, because two strings had
already drifted before anyone wrote this down.
"""
from __future__ import annotations

import ast
import pathlib
import re

DESK = pathlib.Path(__file__).resolve().parent.parent / "desk"

# The declared exceptions, each with the reason it is one.
QUOTED_VOICE = {("capture.py", "PROMPTS")}     # the user's own questions
SECOND_PERSON = re.compile(r"\b(you|your|yours|you're|yourself)\b", re.I)


def _ui_strings(path: pathlib.Path):
    """Every string literal that can reach a screen: module/function/class
    docstrings are excluded (they are for readers of the code), and so is the
    body of any assignment named in QUOTED_VOICE."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = node.body[0] if node.body else None
            if (isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant)
                    and isinstance(doc.value.value, str)):
                skip.add(id(doc.value))
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if any((path.name, n) in QUOTED_VOICE for n in names):
                for sub in ast.walk(node.value):
                    skip.add(id(sub))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in skip):
            yield node.lineno, node.value


def test_the_app_never_speaks_in_the_second_person():
    """The mechanical signature of the register. Two strings had drifted —
    picker.py's "on your clipboard" and record.py's "+ your mic" — and both read
    as the app making a claim about the reader in a product whose whole position
    is that it does not."""
    offenders = [f"{p.name}:{ln}  {s!r}"
                 for p in sorted(DESK.glob("*.py"))
                 for ln, s in _ui_strings(p) if SECOND_PERSON.search(s)]
    assert not offenders, "second person in the app's own voice:\n" + "\n".join(offenders)


def test_the_quoted_voice_is_still_there_and_still_addresses_the_reader():
    """THE CONTROL. The law above is trivially satisfiable by purging every
    "you" in the repo — which would silently destroy the capture prompts, the
    one place desk is SUPPOSED to use second person. The exception has to be
    load-bearing or the law is just a spell-check."""
    from desk import capture
    addressed = [p for p in capture.PROMPTS if SECOND_PERSON.search(p)]
    assert len(addressed) >= 4, capture.PROMPTS
    assert all(p[0].isupper() for p in capture.PROMPTS)   # Title Case = someone else
