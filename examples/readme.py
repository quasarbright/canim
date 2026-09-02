"""The examples in the README, as scenes that actually run.

Rendered to the GIFs the README embeds:

    manim examples/readme.py -qm --format=gif -r 960,320 <SceneName>

Kept in the repo rather than written inline in the docs so the pictures
cannot drift from working code. Each one opens and closes on a still frame
so the loop reads.
"""

from manim import *

from canim import Code, CodeTransform, JAVASCRIPT, PYTHON, theme

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
    """All three outcomes, and the automatic layers get every one of them."""

    def construct(self):
        before = block("root = x ** 0.5")
        after = block("root = math.sqrt(x)")
        self.add(before)
        self.wait(HOLD)
        self.play(CodeTransform(before, after), run_time=1.6)
        self.wait(HOLD)


# Naming the subexpressions — A-normal form, one real compiler pass.
#
# Nothing is duplicated: every name occurs as often on one side as the other.
# What the automatic layers get wrong is *which* same-text token is which.
# There are three `(` in each block and one `=` in the source against three in
# the result, and position in source order is all the greedy layer has to go
# on, so the parens rotate between the three calls and the assignment lands on
# the first new line instead of the last.
ANF_NESTED = "result = f(g(x), h(x))"
ANF_NAMED = "a = g(x)\nb = h(x)\nresult = f(a, b)"


class MappingWrong(Scene):
    """No mapping: the parens swap calls and the `=` picks the wrong line."""

    def construct(self):
        before = block(ANF_NESTED)
        after = block(ANF_NAMED)
        self.add(before)
        self.wait(HOLD)
        # Same arc and timing as `Mapping`, so the only difference between
        # the two GIFs is the mapping itself.
        self.play(CodeTransform(before, after, path_arc=ARC), run_time=2.2)
        self.wait(HOLD * 1.4)


class Mapping(Scene):
    """Four entries: the assignment, and each call's parens.

    Only the openers are named. A delimiter's partner is forced to follow it,
    so all three closers come along without being asked for.
    """

    def construct(self):
        before = block(ANF_NESTED)
        after = block(ANF_NAMED)
        self.add(before)
        self.wait(HOLD)
        self.play(
            CodeTransform(
                before,
                after,
                [
                    ([before.nth("=", 0)], [after.nth("=", 2)]),  # the assignment
                    ([before.nth("(", 0)], [after.nth("(", 2)]),  # f's parens
                    ([before.nth("(", 1)], [after.nth("(", 0)]),  # g's
                    ([before.nth("(", 2)], [after.nth("(", 1)]),  # h's
                ],
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
        # Manim's own GOLD and RED rather than the theme's, so the README can
        # print this line as it stands.
        self.play(
            code.select(code.all("x")).animate.set_color(GOLD),
            run_time=0.8,
        )
        self.wait(HOLD * 0.5)

        # A delimiter and the one that balances it.
        opener = code.nth("(", 0)
        self.play(
            code.select([opener, opener.partner]).animate.set_color(RED),
            run_time=0.8,
        )
        self.wait(HOLD * 0.5)

        # A multi-token ref is one contiguous run, so it gets one box.
        self.play(Create(code.select(code.nth("min(x, hi)")).boxes()), run_time=0.8)
        self.wait(HOLD)
