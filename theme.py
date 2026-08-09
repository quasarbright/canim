"""Token colors, plus the few non-token colors a scene needs around them.

One Dark, minus its background — the video keeps its own darker navy. Only one
theme for now; the shape is here so adding others later doesn't touch anything
else.

Beyond the per-Kind colors there are the colors that aren't syntax: panel fills
and their borders, de-emphasized text, the red for "this is the bad option".
Scenes were carrying those as literals, which meant a new theme would leave
them behind. They live here now. Each one defaults to a value mixed out of the
background, so a new theme gets chrome that at least belongs to its palette
without having to name seven more hexes; a theme that cares can pin them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .lexer import Kind


def _mix(a: str, b: str, t: float) -> str:
    """Blend two hex colors, t=0 giving all `a`."""
    ar, ag, ab = (int(a[i : i + 2], 16) for i in (1, 3, 5))
    br, bg, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (
        round(ar + (br - ar) * t),
        round(ag + (bg - ag) * t),
        round(ab + (bb - ab) * t),
    )


@dataclass(frozen=True)
class Theme:
    name: str
    colors: dict[Kind, str]
    background: str

    # Non-syntax colors. None means "derive from the background" — see
    # __post_init__ for the mix amounts.
    surface: str | None = None  # small boxes: token chips
    surface_stroke: str | None = None
    frame: str | None = None  # large boxes: the labeled frames around groups
    frame_stroke: str | None = None
    muted: str | None = None  # captions — quietest readable text
    subtle: str | None = None  # arrows, connectors — structure, not text
    danger: str = "#e06c75"  # the "no" red; no Kind owns it

    def __post_init__(self) -> None:
        fg = self.colors[Kind.IDENTIFIER]
        for name, amount in (
            ("surface", 0.06),
            ("surface_stroke", 0.22),
            ("frame", 0.05),
            ("frame_stroke", 0.28),
            ("muted", 0.45),
            ("subtle", 0.55),
        ):
            if getattr(self, name) is None:
                object.__setattr__(self, name, _mix(self.background, fg, amount))

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
    # Pinned to what the macros scenes were already using, so lifting them out
    # of that file changed nothing on screen. The derived values are close but
    # not identical.
    surface="#161a24",
    surface_stroke="#2e3444",
    frame="#141824",
    frame_stroke="#39405a",
    muted="#6b7085",
    subtle="#7f8496",
)

ONE_DARK_SLATE = Theme(
    name="one-dark-slate",
    background="#22253a",  # a lifted slate, rather than One Dark's near-black
    colors=dict(ONE_DARK.colors),
    # The surfaces derive correctly here — they come out at the same 1.1:1 and
    # 1.5:1 lift they have on One Dark's background — but `muted` and `subtle`
    # do not. Mixing toward the foreground from a background this light lands
    # captions at 2.6:1 where One Dark has 3.9:1, so those two are pinned to
    # hold the relationship the scenes were built against.
    muted="#7d8194",
    subtle="#9396a5",
)

VIVID_BLUE = Theme(
    name="vivid-blue",
    background="#08004d",
    colors={
        Kind.IDENTIFIER: "#c5d8f5",
        Kind.KEYWORD: "#ee5382",  # rose
        Kind.BUILTIN: "#2fe5ee",  # aqua
        Kind.LITERAL: "#f4a65d",  # amber
        Kind.STRING: "#70ff88",  # green
        Kind.COMMENT: "#5896b6",
        Kind.OPERATOR: "#ee5382",  # keyword's rose, same reasoning as One Dark
        Kind.DELIMITER: "#c5d8f5",
        Kind.PUNCTUATION: "#c5d8f5",
    },
    # All pinned. The derivation mixes toward the foreground, which on a
    # background this saturated washes the surfaces gray and lands captions at
    # 3.3:1; these keep the background's own hue and lift by lightness instead.
    surface="#11085f",
    surface_stroke="#2c2287",
    frame="#0d0558",
    frame_stroke="#352b93",
    muted="#918bc8",
    subtle="#7c75b8",
    danger="#f97ba3",
)

# What a `Code` block gets when nobody says otherwise. A video that wants a
# different palette sets its own module-level theme and passes it in, rather
# than reassigning this — see `2026/macros/main.py`.
DEFAULT = ONE_DARK_SLATE

# Set once here so every scene and every Code block agrees.
FONT = "Monaco"
FONT_SIZE = 28
LINE_SPACING = 0.7
