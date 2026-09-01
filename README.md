# canim

Code transformation animations for [manim](https://www.manim.community/).

Animates one block of code becoming another token by token, rather than by
text diff. A name that moves, moves. A name that splits in two, splits. A
token with no counterpart fades.

```python
from manim import Scene
from canim import Code, CodeTransform, PYTHON

class Rewrite(Scene):
    def construct(self):
        before = Code("x = f(a) + f(b)", PYTHON)
        after = Code("x = g(a, b)", PYTHON)
        self.add(before)
        self.play(CodeTransform(before, after))
```

## Install

    pip install -e .

Python 3.12 only. The upper bound is real: ManimPango 0.5.0 has no 3.13 wheel
and fails to build from source.

## How it works

Lex, match, animate.

**Glyph identity.** A `Code` block is one manim `Text` holding the whole
source. Manim emits one submobject per character, whitespace included, so a
token's character offset *is* its glyph index and a run of tokens is always a
contiguous glyph range. The constructor asserts this; if a font ever breaks
the assumption, everything downstream silently colors and animates the wrong
glyphs.

**Lexing is stateless.** A token's kind is a pure function of its own text —
no lookbehind, no parser state — so colors cannot flicker on the intermediate
frames of a transform, which are usually valid in no language at all. The cost
is that a name being *defined* cannot be told from one being *used*.

**Matching is three layers**, each seeing only what the previous did not
claim: the hand-written mapping, then greedy same-text pairing in source order
with delimiter partners forced, then fade. Only the mapping raises — it is an
assertion, while the other two always have an answer.

**Debug the mapping, not the render.** A wrong-but-valid correspondence
renders a perfectly correct final frame, so looking at pixels proves nothing:

```python
from canim import dump, match
dump(before.tokens, after.tokens, match(before.tokens, after.tokens))
```

That prints a table of what travels where and whether it was asserted or
guessed. Most mapping bugs are a token flying somewhere it has no business
going, and this is the only way to see it.

## Themes

A theme carries a color per token kind plus the non-syntax colors a scene
needs around them — panel fills, borders, de-emphasized text, a red for the
bad option. The non-syntax ones default to a value mixed out of the
background, so a new theme gets coherent chrome without naming seven more
hexes; a theme that cares can pin them.

Five ship with the library, as objects, so nothing needs a path:

```python
from canim import theme
theme.ONE_DARK_SLATE          # also ONE_DARK, PASTEL_EVENING, MONOKAI, SOLARIZED_DARK
theme.BUILT_IN["monokai"]     # by name
theme.DEFAULT                 # one-dark-slate
```

Your own live wherever you keep them, as flat `.theme.json`, loaded by path:

```python
theme.open("~/videos/themes/marine.theme.json")
```

A file records only the chrome it pins. Writing a derived value back would
freeze it and stop it following the background.

## The theme editor

    python -m canim.theme_editor

A local server plus a page, for building a palette by eye with the numbers
visible. It lists canim's five and everything in `<cwd>/themes`; `--themes
<dir>` points it at more. Saving one of canim's own diverts to Save As —
editing `one-dark` in the editor must not change what every video that
imports it renders as.

The page holds no lexer and no color math. Both live in canim and are asked
for over the API, so the preview is what a render produces rather than a
second implementation that drifts.

`palette.py` is the color math, pure functions over hex strings:

**OKLCH, not HSL.** HSL's lightness is not perceptual — `#1aff47` and
`#0000ff` are both "50%" and one is blinding beside the other. Picking a
palette in HSL turns into hunting a lightness per hue; in OKLCH one lightness
reads as one brightness across the wheel.

**Contrast and separation are different questions.** Contrast is against the
background and decides legibility. Separation is between two token colors and
decides whether you can tell a comment from a keyword. A color can pass one
and fail the other.

**Separation scores three axes and takes the best.** Colors differ by
lightness, by how colorful they are, or by hue, and any one is enough on its
own. A single distance metric cannot do this — One Dark's identifier/builtin
and marine's keyword/builtin have nearly identical chroma *distance* and
opposite verdicts, because a near-gray beside a cyan is obvious while two
equally-saturated teals are not. Hue only counts when both colors have enough
chroma to show one. The calibration table is in the docstring; if a real pair
is ever judged wrong, add it there and re-derive the thresholds rather than
nudging a number.

## Video color metadata

Manim writes H.264 with no color metadata, so every player guesses. QuickTime
guesses BT.709 with a video transfer curve and color-manages to the display,
which is why a render looks brighter and more saturated than the same hex does
in a browser. Call this once from a video's module:

```python
from canim.video import tag_color_space
tag_color_space()
```

The correct tags are BT.601, not BT.709 — manim's RGB→YUV conversion uses 601
coefficients even at 720p. Established by tagging a real render three ways and
measuring how far the decode drifted from the source colors:

| matrix | | total error across four colors |
|---|---|---|
| 1 | bt709 | 42 |
| 5 | bt470bg | 4 |
| 6 | smpte170m | 4 |

Tagging only changes what the file declares, not what is encoded.

## Tests

    pytest canim

## License

MIT.
