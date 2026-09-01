"""The examples in the README, as scenes that actually run.

Rendered to the GIFs the README embeds:

    manim examples/readme.py -qm --format=gif -r 960,320 <SceneName>

Kept in the repo rather than written inline in the docs so the pictures
cannot drift from working code. Each one opens and closes on a still frame
so the loop reads.
"""

from manim import *

from canim import Code, CodeTransform, Kind, LISP, PYTHON, theme

THEME = theme.ONE_DARK_SLATE
config.background_color = THEME.background

FONT_SIZE = 44
HOLD = 0.9


def block(source: str, language=LISP) -> Code:
    return Code(source, language, font_size=FONT_SIZE, theme=THEME)


class Basic(Scene):
    """A transform with no help: what moves, what fades."""

    def construct(self):
        before = block("(swap a b)")
        after = block("(rotate a b c)")
        self.add(before)
        self.wait(HOLD)
        self.play(CodeTransform(before, after), run_time=1.6)
        self.wait(HOLD)


class Mapping(Scene):
    """One token becoming two, because the mapping says so."""

    def construct(self):
        before = block("(let ((tmp a))\n  (setf a tmp))")
        after = block("(let ((g1 a))\n  (setf a g1))")
        self.add(before)
        self.wait(HOLD)
        self.play(
            CodeTransform(before, after, [(["tmp"], after.all("g1"))]),
            run_time=1.6,
        )
        self.wait(HOLD)


class Highlighting(Scene):
    """Selections: color the tokens you name, box the runs you name."""

    def construct(self):
        code = block("(defmacro swap (a b)\n  `(let ((tmp ,a))\n     (setf ,a ,b)))")
        self.add(code)
        self.wait(HOLD * 0.6)

        # Every `a` and `b`, wherever they appear — including under a comma.
        self.play(
            code.select(code.all("a") + code.all("b")).animate.set_color(
                THEME.colors[Kind.LITERAL]
            ),
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

        self.play(Create(code.select(code.all("tmp")).boxes()), run_time=0.8)
        self.wait(HOLD)


class Python(Scene):
    """Another language, and a longer rewrite."""

    def construct(self):
        before = block("total = sum([f(x) for x in xs])", PYTHON)
        after = block("total = sum(f(x) for x in xs)", PYTHON)
        self.add(before)
        self.wait(HOLD)
        self.play(CodeTransform(before, after), run_time=1.6)
        self.wait(HOLD)
