"""The on-screen code block.

One ``Text`` holding the whole source, with tokens addressed as glyph slices
into it. Manim emits one submobject per character — whitespace included — so a
token's character offset *is* its glyph index, and a run of tokens is always a
contiguous glyph range even across line breaks.

Layout is entirely Pango's: the font is monospace, so columns and baselines come
out right without any grid arithmetic here.
"""

from __future__ import annotations

from collections.abc import Iterable

from manim import VGroup, Text

from . import theme as theme_module
from .languages import resolve
from .lexer import Language, Token, lex
from .refs import TokenRef, _nth, find_runs
from .theme import Theme

TokenLike = str | int | Token | TokenRef
Refs = TokenLike | Iterable[TokenLike]


class Code(VGroup):
    def __init__(
        self,
        source: str,
        language: Language | str,
        *,
        font: str | None = None,
        font_size: float | None = None,
        line_spacing: float | None = None,
        theme: Theme | None = None,
        **kwargs,
    ):
        self.source = source
        self.language = resolve(language)
        self.theme = theme or theme_module.DEFAULT

        self.tokens: list[Token] = lex(source, self.language)

        self.text = Text(
            source,
            font=font or theme_module.FONT,
            font_size=font_size if font_size is not None else theme_module.FONT_SIZE,
            line_spacing=(
                line_spacing if line_spacing is not None else theme_module.LINE_SPACING
            ),
            disable_ligatures=True,
        )

        # The identity between character offset and glyph index is the single
        # assumption everything else rests on. If a font ever breaks it, fail
        # here rather than silently coloring and animating the wrong glyphs.
        if len(self.text) != len(source):
            raise AssertionError(
                f"expected one glyph per character: {len(source)} characters "
                f"produced {len(self.text)} glyphs. Ligatures or an unusual font?"
            )

        super().__init__(self.text, **kwargs)
        self._apply_theme()

    # --- addressing --------------------------------------------------------

    def indices(self, refs: Refs) -> tuple[int, ...]:
        """Normalize anything token-shaped into a sorted tuple of token indices.

        A bare string means the first occurrence of that token, the same as it
        does in a mapping entry — so `select("tmp")` and `[["tmp"], ...]` agree
        about what a string is.
        """
        if isinstance(refs, (str, int, Token, TokenRef)):
            refs = [refs]
        out: list[int] = []
        for ref in refs:
            if isinstance(ref, str):
                out.extend(self.nth(ref).indices)
            elif isinstance(ref, TokenRef):
                out.extend(ref.indices)
            elif isinstance(ref, Token):
                out.append(ref.index)
            else:
                out.append(int(ref))
        return tuple(sorted(set(out)))

    def group(self, refs: Refs) -> VGroup:
        """The glyphs for those tokens, as one VGroup.

        A contiguous run comes out as a single slice, so the whitespace between
        its tokens travels with it — which is what makes a multi-token group
        move as a unit rather than as scattered characters.
        """
        indices = self.indices(refs)
        if not indices:
            return VGroup()

        glyphs = VGroup()
        for start, end in _runs(indices):
            glyphs.add(*self.text[self.tokens[start].start : self.tokens[end].end])
        return glyphs

    # --- refs --------------------------------------------------------------

    def nth(self, pattern: str, index: int = 0) -> TokenRef:
        """The `index`-th occurrence of `pattern`, as one token or a run."""
        return _nth(self, pattern, index)

    def all(self, pattern: str) -> list[TokenRef]:
        """Every occurrence, as a list — drops straight into an entry slot."""
        runs = find_runs(self.tokens, pattern, self.language)
        if not runs:
            from .refs import RefError

            raise RefError(
                f"{pattern!r} does not appear in {self.source!r} as a run of tokens"
            )
        return [TokenRef(self, r, f"{pattern}#{i}") for i, r in enumerate(runs)]

    def select(self, refs: Refs) -> Selection:
        """The tokens those refs name, as something you can animate directly.

        The door to everything per-token. A `Selection` is a `VGroup`, so
        `sel.animate.set_color(...)` and friends work as they do anywhere else
        in manim; `sel.runs` and `sel.boxes()` cover the things that need
        geometry rather than a tween.
        """
        return Selection(self, refs)

    def clone(self) -> Code:
        """A second block identical to this one, transforms included.

        The peel-off: add both, then transform one while the other stays put,
        and the copy reads as having lifted off the original.

        A copy rather than a rebuild from the constructor arguments — a rebuilt
        block loses anything applied afterwards, so a scaled block cloned itself
        back to full size and sat on top of the original, doubled.
        """
        return self.copy()

    def token_group(self, index: int) -> VGroup:
        token = self.tokens[index]
        return self.text[token.start : token.end]

    # --- appearance --------------------------------------------------------

    def _apply_theme(self) -> None:
        for token in self.tokens:
            self.text[token.start : token.end].set_color(self.theme.color(token.kind))

    def __repr__(self) -> str:
        head = self.source.splitlines()[0] if self.source else ""
        more = "…" if "\n" in self.source else ""
        return f"<Code {self.language.name} {len(self.tokens)} tokens {head!r}{more}>"


class Selection(VGroup):
    """Glyphs for a set of tokens, plus the handles that need geometry."""

    def __init__(self, code: Code, refs: Refs):
        self.code = code
        self.indices = code.indices(refs)
        self.tokens = [code.tokens[i] for i in self.indices]
        # One VGroup per contiguous run. Disjoint tokens must be boxed
        # separately — a single box round the whole selection would span
        # everything in between.
        self.runs = VGroup(
            *[code.group(range(a, b + 1)) for a, b in _runs(self.indices)]
        )
        super().__init__(*[glyph for run in self.runs for glyph in run])

    def boxes(self, **kwargs) -> VGroup:
        """A rectangle round each contiguous run."""
        from manim import SurroundingRectangle

        kwargs.setdefault("buff", 0.05)
        kwargs.setdefault("stroke_width", 2)
        return VGroup(*[SurroundingRectangle(run, **kwargs) for run in self.runs])

    def __repr__(self) -> str:
        texts = " ".join(t.text for t in self.tokens)
        return f"<Selection {len(self.tokens)} tokens {texts!r}>"


def _runs(indices: tuple[int, ...]) -> list[tuple[int, int]]:
    """Collapse sorted indices into (first, last) contiguous runs."""
    runs: list[tuple[int, int]] = []
    start = prev = indices[0]
    for i in indices[1:]:
        if i == prev + 1:
            prev = i
            continue
        runs.append((start, prev))
        start = prev = i
    runs.append((start, prev))
    return runs
