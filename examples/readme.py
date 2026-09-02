"""The examples in the README, as scenes that actually run.

Rendered to the GIFs the README embeds:

    manim examples/readme.py -qm --format=gif -r 960,320 <SceneName>

Kept in the repo rather than written inline in the docs so the pictures
cannot drift from working code. Each one opens and closes on a still frame
so the loop reads.
"""

from manim import *

from canim import Code, CodeTransform, JAVASCRIPT, Kind, PYTHON, theme

THEME = theme.ONE_DARK_SLATE
config.background_color = THEME.background

FONT_SIZE = 44
HOLD = 0.9
ARC = 0.7  # curves the moving glyphs, so two copies of one token visibly fan out


def block(source: str, language=PYTHON) -> Code:
    return Code(source, language, font_size=FONT_SIZE, theme=THEME)


# Scenes are in the order the README uses them.


class Languages(Scene):
    """The opening example: the same function in two languages.

    Nothing here is asserted. Both `a`s and both `b`s pair correctly on their
    own, because each appears the same number of times on both sides and in
    the same order — which is exactly the condition the automatic layers need.
    """

    def construct(self):
        before = block("def add(a, b):\n    return a + b", PYTHON)
        after = block("function add(a, b) {\n  return a + b;\n}", JAVASCRIPT)
        self.add(before)
        self.wait(HOLD)
        self.play(CodeTransform(before, after), run_time=1.6)
        self.wait(HOLD)


class Basic(Scene):
    """All three outcomes in one line: move, fade out, fade in."""

    def construct(self):
        before = block("print(msg)")
        after = block("log.info(msg)")
        self.add(before)
        self.wait(HOLD)
        self.play(CodeTransform(before, after), run_time=1.6)
        self.wait(HOLD)


# A call, and the same thing with the call inlined. Each argument is used
# twice in the result, which is the case the automatic layers cannot cover:
# they pair by text in source order, and there is only one `dx` to go around.
INLINE_CALL = "dist = hypot(dx, dy)"
INLINE_BODY = "dist = sqrt(dx * dx + dy * dy)"


class MappingWrong(Scene):
    """The same inlining with no mapping — half the names appear from nowhere."""

    def construct(self):
        before = block(INLINE_CALL)
        after = block(INLINE_BODY)
        self.add(before)
        self.wait(HOLD)
        # Same arc and timing as `Mapping`, so the only difference between
        # the two GIFs is the mapping itself.
        self.play(CodeTransform(before, after, path_arc=ARC), run_time=2.2)
        self.wait(HOLD * 1.4)


class Mapping(Scene):
    """One token becoming several, because the mapping says so."""

    def construct(self):
        before = block(INLINE_CALL)
        after = block(INLINE_BODY)
        self.add(before)
        self.wait(HOLD)
        self.play(
            CodeTransform(
                before,
                after,
                [(["dx"], after.all("dx")), (["dy"], after.all("dy"))],
                path_arc=ARC,
            ),
            run_time=2.2,
        )
        self.wait(HOLD * 1.4)


class Highlighting(Scene):
    """Selections: color the tokens you name, box the runs you name."""

    def construct(self):
        code = block(
            "# keep x within [lo, hi]\n"
            "def clamp(x, lo, hi):\n"
            "    return max(lo, min(x, hi))"
        )
        self.add(code)
        self.wait(HOLD * 0.6)

        # Both `x` tokens. Not the `x` in the comment: refs resolve against
        # tokens, and a comment is one token whose text happens to contain it.
        self.play(
            code.select(code.all("x")).animate.set_color(THEME.colors[Kind.LITERAL]),
            run_time=0.8,
        )
        self.wait(HOLD * 0.5)

        # A delimiter and the one that balances it.
        opener = code.nth("(", 0)
        self.play(
            code.select([opener, opener.partner]).animate.set_color(THEME.danger),
            run_time=0.8,
        )
        self.wait(HOLD * 0.5)

        # A multi-token ref is one contiguous run, so it gets one box.
        self.play(Create(code.select(code.nth("min(x, hi)")).boxes()), run_time=0.8)
        self.wait(HOLD)
