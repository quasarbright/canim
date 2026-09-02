"""Seeing the correspondence.

A transform's last frame is the destination however the tokens got there, so
watching a render proves nothing about whether the motion was right. The
correspondence, though, is a static fact — which makes it exactly the thing a
single ``-s`` frame can verify.

Each token is labelled with where it goes: ``3->6`` on the source, ``6<-3`` on
the destination, ``3->6,9`` for a clone, ``6<-3,5`` for a merge, ``·`` for a
fade. Labels are underlined when the correspondence came from a mapping entry
rather than being inferred, because the first question about a wrong arrow is
always whether it was asserted or guessed.

Color says what happens to the token: cyan for one that travels with its text
intact however many copies it ends up as, yellow for one whose text changes,
red for gone, green for new.
"""

from __future__ import annotations

from manim import DOWN, LEFT, RIGHT, UP, Text, Underline, VGroup

from .code import Code
from .matcher import Correspondence, Op
from .matcher import match as run_match
from .refs import resolve_mapping

DEBUG_LINE_SPACING = 1.9
"""Debug blocks need room between lines for the labels to sit in.

The video's own spacing is tight by design, which leaves nowhere to put a label
except on top of the line above it. Build blocks for a correspondence view with
`debug_block`, or pass `line_spacing` yourself.
"""


def debug_block(source: str, language, **kwargs) -> Code:
    kwargs.setdefault("line_spacing", DEBUG_LINE_SPACING)
    return Code(source, language, **kwargs)


TRAVELS = "#56b6c2"   # cyan — same text, wherever it ends up
CHANGES = "#e5c07b"   # yellow — the text itself is different
GONE = "#e06c75"      # red
NEW = "#98c379"       # green
UNKNOWN = "#7f8496"


def link_color(op: Op, same_text: bool) -> str:
    """Color by what happens to the token, not by the name of the op.

    A clone whose copies keep their text is a move that happens twice — it
    belongs with the moves. Only a genuine change of text earns its own color,
    so scanning for yellow finds the morphs rather than every duplication.

    On a label that lists several counterparts, yellow is infectious: `1->2,4`
    goes yellow if *either* of those links changes the text, because the label
    is one claim about the whole split. The individual labels on the other side
    each describe one link, so they stay colored on their own terms — a split
    into one same word and one different word reads yellow on the source, cyan
    on one destination and yellow on the other.
    """
    if op is Op.FADE_OUT:
        return GONE
    if op is Op.FADE_IN:
        return NEW
    return TRAVELS if same_text else CHANGES

NONE = "·"


def targets(correspondence: Correspondence) -> tuple[dict, dict]:
    """Per-token destinations and origins for one correspondence.

    Groups pair positionally, matching how they animate, so a five-token run
    labels each of its tokens with its own counterpart rather than with the
    whole run.
    """
    forward: dict[int, list[int]] = {}
    backward: dict[int, list[int]] = {}
    op = correspondence.op

    def link(i: int, j: int) -> None:
        forward.setdefault(i, []).append(j)
        backward.setdefault(j, []).append(i)

    if op in (Op.MOVE, Op.MORPH):
        for a, b in zip(correspondence.src[0], correspondence.dst[0]):
            link(a, b)
    elif op is Op.CLONE:
        for group in correspondence.dst:
            for a, b in zip(correspondence.src[0], group):
                link(a, b)
    elif op is Op.MERGE:
        for group in correspondence.src:
            for a, b in zip(group, correspondence.dst[0]):
                link(a, b)

    for i in correspondence.src_tokens:
        forward.setdefault(i, [])
    for j in correspondence.dst_tokens:
        backward.setdefault(j, [])
    return forward, backward


def correspondence_labels(
    source: Code,
    dest: Code,
    mapping=(),
    *,
    font_size: float = 11,
    dim: float = 0.28,
) -> VGroup:
    """Labels for both blocks. Add the result to the scene.

    Labels sit *on* their tokens rather than above them, which needs no room
    between lines and keeps a label next to the thing it describes however long
    the block is. The code is dimmed so the labels are the foreground.
    """
    entries = resolve_mapping(mapping, source, dest)
    correspondences = run_match(source.tokens, dest.tokens, entries)

    forward: dict[int, list[int]] = {}
    backward: dict[int, list[int]] = {}
    color_of: dict[tuple[str, int], str] = {}
    manual: set[tuple[str, int]] = set()

    for c in correspondences:
        f, b = targets(c)
        forward.update(f)
        backward.update(b)
        for i in c.src_tokens:
            same = all(
                source.tokens[i].text == dest.tokens[j].text for j in f.get(i, [])
            )
            color_of[("s", i)] = link_color(c.op, same)
            if c.manual:
                manual.add(("s", i))
        for j in c.dst_tokens:
            same = all(
                dest.tokens[j].text == source.tokens[i].text for i in b.get(j, [])
            )
            color_of[("d", j)] = link_color(c.op, same)
            if c.manual:
                manual.add(("d", j))

    source.set_opacity(dim)
    dest.set_opacity(dim)

    labels = VGroup()
    labels.add(
        *_side(source, forward, color_of, manual, "s", "->", font_size),
        *_side(dest, backward, color_of, manual, "d", "<-", font_size),
    )
    return labels


def _side(code, links, color_of, manual, side, arrow, font_size):
    out = []
    for token in code.tokens:
        others = links.get(token.index, [])
        text = f"{token.index}{arrow}" + (
            ",".join(str(x) for x in others) if others else NONE
        )
        label = Text(
            text,
            font="Helvetica",
            font_size=font_size,
            color=color_of.get((side, token.index), UNKNOWN),
        )
        glyphs = code.group(token)
        # Two rows within the line, alternating. A label is several characters
        # wide over a cell that may be one, so neighbours would overlap on a
        # single row — `2->5,10` sitting on a lone `a` is six cells of text.
        row = 0.11 if token.index % 2 else -0.11
        # Center on the line rather than the token's ink: `(` and `x` have very
        # different ink boxes, and a label riding the ink lands at a different
        # height for each one.
        label.move_to(
            [glyphs.get_center()[0], _line_middle(code, token.line) + row, 0]
        )
        out.append(label)
        if (side, token.index) in manual:
            out.append(
                Underline(label, buff=0.012, stroke_width=1.0, color=label.color)
            )
    return out


def _line_middle(code, line: int) -> float:
    tokens = [t for t in code.tokens if t.line == line]
    tops = [code.group(t).get_top()[1] for t in tokens]
    bottoms = [code.group(t).get_bottom()[1] for t in tokens]
    return (max(tops) + min(bottoms)) / 2


def correspondence_view(
    source: Code, dest: Code, mapping=(), *, buff: float = 2.2
) -> VGroup:
    """Both blocks stacked with their labels — the whole thing in one mobject."""
    VGroup(source, dest).arrange(DOWN, buff=buff, aligned_edge=LEFT)
    return VGroup(source, dest, correspondence_labels(source, dest, mapping))
