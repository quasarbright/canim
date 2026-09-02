"""Shared fixtures.

`Code` takes a language with no default, on purpose — a block silently lexed
as the wrong language colors and matches wrongly with nothing to notice. The
tests still want a one-word constructor, and most of them are about matching
rather than about any particular syntax, so they say `lisp(...)`.
"""

from canim import Code, LISP


def lisp(source: str, **kwargs) -> Code:
    return Code(source, LISP, **kwargs)
