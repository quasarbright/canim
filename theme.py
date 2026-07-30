"""Token colors.

One Dark, minus its background — the video keeps its own darker navy. Only one
theme for now; the shape is here so adding others later doesn't touch anything
else.
"""

from __future__ import annotations

from dataclasses import dataclass

from .lexer import Kind


@dataclass(frozen=True)
class Theme:
    name: str
    colors: dict[Kind, str]
    background: str

    def color(self, kind: Kind) -> str:
        return self.colors[kind]

    def __deepcopy__(self, memo):
        # Immutable and shared by every block; see Language.__deepcopy__.
        return self


ONE_DARK = Theme(
    name="one-dark",
    background="#0e0f16",  # not One Dark's #282c34 — matches the video's palette
    colors={
        Kind.IDENTIFIER: "#abb2bf",  # foreground
        Kind.KEYWORD: "#c678dd",  # purple
        Kind.BUILTIN: "#56b6c2",  # cyan
        Kind.LITERAL: "#d19a66",  # orange — numbers, #t, None
        Kind.STRING: "#98c379",  # green
        Kind.COMMENT: "#5c6370",
        # Same pink as keywords. An unquote comma and a `let` are both syntax
        # doing work, so they read as one category — and it keeps the commas
        # clearly off the delimiters without adding another hue.
        Kind.OPERATOR: "#c678dd",
        Kind.DELIMITER: "#abb2bf",
        Kind.PUNCTUATION: "#abb2bf",
    },
)

DEFAULT = ONE_DARK

# Set once here so every scene and every Code block agrees.
FONT = "Monaco"
FONT_SIZE = 28
LINE_SPACING = 0.7
