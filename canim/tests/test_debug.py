from canim import Code
from canim.debug import correspondence_labels, debug_block, targets
from canim.matcher import Correspondence, Op
from canim.refs import resolve_mapping


def test_move_links_groups_positionally():
    c = Correspondence(Op.MOVE, src=((1, 2, 3),), dst=((7, 8, 9),))
    forward, backward = targets(c)
    assert forward == {1: [7], 2: [8], 3: [9]}
    assert backward == {7: [1], 8: [2], 9: [3]}


def test_clone_links_one_source_to_every_destination():
    c = Correspondence(Op.CLONE, src=((2,),), dst=((5,), (10,)))
    forward, backward = targets(c)
    assert forward == {2: [5, 10]}
    assert backward == {5: [2], 10: [2]}


def test_merge_links_every_source_to_the_one_destination():
    c = Correspondence(Op.MERGE, src=((3,), (7,)), dst=((4,),))
    forward, backward = targets(c)
    assert forward == {3: [4], 7: [4]}
    assert backward == {4: [3, 7]}


def test_fades_have_no_counterpart():
    forward, _ = targets(Correspondence(Op.FADE_OUT, src=((1,),)))
    assert forward == {1: []}
    _, backward = targets(Correspondence(Op.FADE_IN, dst=((2,),)))
    assert backward == {2: []}


def test_every_token_on_both_sides_gets_a_label():
    src, dst = debug_block("(f (x y))"), debug_block("(f x y)")
    labels = correspondence_labels(src, dst)
    # no underlines here, so one label per token
    assert len(labels) == len(src.tokens) + len(dst.tokens)


def test_manual_correspondences_are_underlined():
    from manim import Underline

    src = debug_block("(swap! a b)")
    dst = debug_block("(let ([tmp a]) (set! a b))")
    plain = correspondence_labels(src, dst)
    assert not any(isinstance(m, Underline) for m in plain)

    marked = correspondence_labels(src, dst, [(["a"], dst.all("a"))])
    assert any(isinstance(m, Underline) for m in marked)


def test_debug_blocks_are_looser_than_video_blocks():
    # Labels sit between lines; the video's own spacing leaves no room.
    from canim.debug import DEBUG_LINE_SPACING
    from canim.theme import LINE_SPACING

    assert DEBUG_LINE_SPACING > LINE_SPACING
    tight = Code("(a)\n(b)")
    loose = debug_block("(a)\n(b)")
    assert loose.height > tight.height


# --- color ----------------------------------------------------------------


def label_colors(source, dest, mapping=()):
    from canim.debug import correspondence_labels

    out = {}
    for m in correspondence_labels(source, dest, mapping):
        text = getattr(m, "text", None)
        if text:
            out[text] = m[0].get_color().to_hex().lower()
    return out


def test_a_clone_that_keeps_its_text_is_not_a_change():
    from canim.debug import TRAVELS

    src, dst = Code("(swap! a b)"), Code("(let ([tmp a]) (set! a b))")
    colors = label_colors(src, dst, [(["a"], dst.all("a"))])
    assert colors["2->5,10"] == TRAVELS.lower()


def test_a_clone_into_different_words_is_a_change():
    from canim.debug import CHANGES

    src, dst = Code("(swap! a b)"), Code("(let (set! a b))")
    colors = label_colors(
        src, dst, [(["swap!"], [dst.nth("let"), dst.nth("set!")])]
    )
    assert colors["1->1,3"] == CHANGES.lower()


def test_change_is_infectious_on_a_grouped_label_only():
    """A split into one same word and one different word.

    The source label is one claim about the whole split, so it takes the change
    color. The destination labels each describe a single link, so they stay
    colored on their own terms.
    """
    from canim.debug import CHANGES, TRAVELS

    src, dst = Code("(f a)"), Code("(g a b)")
    colors = label_colors(src, dst, [(["a"], [dst.nth("a"), dst.nth("b")])])

    assert colors["2->2,3"] == CHANGES.lower()  # infectious
    assert colors["2<-2"] == TRAVELS.lower()  # a -> a, unchanged
    assert colors["3<-2"] == CHANGES.lower()  # a -> b, changed


def test_a_plain_morph_is_a_change():
    from canim.debug import CHANGES

    src, dst = Code("(let x)"), Code("(lambda x)")
    colors = label_colors(src, dst, [(["let"], ["lambda"])])
    assert colors["1->1"] == CHANGES.lower()
    assert colors["1<-1"] == CHANGES.lower()
