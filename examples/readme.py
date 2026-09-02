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
    """Naming the subexpressions — A-normal form, one compiler pass.

    Unaided and correct. The three paren pairs do rotate among themselves,
    which is invisible: they are identical glyphs landing in the right places.
    """

    def construct(self):
        before = block("result = f(g(x), h(x))")
        after = block("a = g(x)\nb = h(x)\nresult = f(a, b)")
        self.add(before)
        self.wait(HOLD)
        self.play(CodeTransform(before, after), run_time=1.8)
        self.wait(HOLD)


# A C-style `for` and the same loop as a `while`. In JavaScript this rewrite
# is exact: the header really does hold an init, a test and an increment, and
# the while form just puts each one where it runs.
#
# `i` appears four times on both sides, so nothing is duplicated — but the
# order differs. Source: init, test, increment, body. Destination: init, test,
# body, increment. The greedy layer pairs by position among same-text tokens,
# so the last two cross.
FOR_LOOP = "for (let i = 0; i < n; i++) {\n  total += i\n}"
WHILE_LOOP = "let i = 0\nwhile (i < n) {\n  total += i\n  i++\n}"


def mark(code: Code) -> None:
    """Color the two `i` tokens that trade places.

    Only so they can be followed. Coloring the *source* rather than the
    result is the point: the marks ride their glyphs through the transform,
    so where each one lands is the answer rather than a claim about it.
    """
    code.select(code.nth("i", 2)).set_color(GOLD)   # the header's increment
    code.select(code.nth("i", 3)).set_color(GREEN)  # the body's use


class MappingWrong(Scene):
    """No mapping: the increment's `i` and the body's `i` trade places."""

    def construct(self):
        before = block(FOR_LOOP, JAVASCRIPT)
        after = block(WHILE_LOOP, JAVASCRIPT)
        mark(before)
        self.add(before)
        self.wait(HOLD)
        # Same marks, arc and timing as `Mapping`, so the only difference
        # between the two GIFs is the mapping itself.
        self.play(CodeTransform(before, after, path_arc=ARC), run_time=2.4)
        self.wait(HOLD * 1.4)


class Mapping(Scene):
    """Two entries, saying which `i` is which."""

    def construct(self):
        before = block(FOR_LOOP, JAVASCRIPT)
        after = block(WHILE_LOOP, JAVASCRIPT)
        mark(before)
        self.add(before)
        self.wait(HOLD)
        self.play(
            CodeTransform(
                before,
                after,
                [
                    ([before.nth("i", 2)], [after.nth("i", 3)]),  # the increment
                    ([before.nth("i", 3)], [after.nth("i", 2)]),  # the body
                ],
                path_arc=ARC,
            ),
            run_time=2.4,
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
