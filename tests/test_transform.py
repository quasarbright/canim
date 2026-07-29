"""Transform tests. These check scene bookkeeping, not how it looks."""

import pytest
from manim import Scene

from canim import Code, CodeTransform
from canim.matcher import Op


def played(source, dest, mapping=()):
    """Run the animation's lifecycle against a real Scene, minus rendering."""
    scene = Scene()
    scene.add(source)
    anim = CodeTransform(source, dest, mapping)
    anim._setup_scene(scene)
    scene.add_mobjects_from_animations([anim])  # what Scene.play does
    anim.begin()
    anim.interpolate(1.0)
    anim.finish()
    anim.clean_up_from_scene(scene)
    return scene, anim


def test_scene_ends_holding_exactly_dest():
    # The glyph slices are temporary VGroups over dest.text's children, so a
    # sloppy cleanup leaves both them and dest in the scene, drawing every
    # glyph twice.
    src, dst = Code("(a + b)"), Code("(+ a b)")
    scene, _ = played(src, dst)
    assert scene.mobjects == [dst]


def test_source_is_gone():
    src, dst = Code("(f (x y))"), Code("(f x y)")
    scene, _ = played(src, dst)
    assert src not in scene.mobjects


def test_reorder_is_all_moves():
    src, dst = Code("(a + b)"), Code("(+ a b)")
    _, anim = played(src, dst)
    assert {c.op for c in anim.correspondences} == {Op.MOVE}


def test_flatten_moves_and_fades():
    src, dst = Code("(f (x y))"), Code("(f x y)")
    _, anim = played(src, dst)
    ops = {c.op for c in anim.correspondences}
    assert ops == {Op.MOVE, Op.FADE_OUT}


def test_one_animation_per_glyph_pair():
    # Multi-character tokens pair glyph by glyph, so we never hand manim two
    # mismatched VGroups and let align_data pad them into a smear.
    src, dst = Code("(let x)"), Code("(x let)")
    _, anim = played(src, dst)
    assert len(anim.animations) == len(src.source.replace(" ", ""))


# --- morph -----------------------------------------------------------------


def test_morph_with_a_shared_prefix_pairs_glyphs():
    # `tmp` -> `tmp_G4271`: the shared prefix should hold still and the suffix
    # grow out of it, so this pairs glyph by glyph rather than cross-fading.
    from manim import FadeTransform

    src, dst = Code("(f tmp)"), Code("(f tmp_G4271)")
    anim = CodeTransform(src, dst, [(["tmp"], ["tmp_G4271"])])
    assert not any(isinstance(a, FadeTransform) for a in anim.animations)


def test_morph_between_unlike_words_cross_fades():
    # `let` -> `lambda` shares only `l`; pairing would give e->a, t->m in
    # place, which reads as mush.
    from manim import FadeTransform

    src, dst = Code("(let x)"), Code("(lambda x)")
    anim = CodeTransform(src, dst, [(["let"], ["lambda"])])
    assert any(isinstance(a, FadeTransform) for a in anim.animations)


def test_morph_is_flagged_manual():
    src, dst = Code("(let x)"), Code("(lambda x)")
    anim = CodeTransform(src, dst, [(["let"], ["lambda"])])
    morphs = [c for c in anim.correspondences if c.op is Op.MORPH]
    assert len(morphs) == 1 and morphs[0].manual


def test_scene_still_ends_clean_with_a_mapping():
    src, dst = Code("(let x)"), Code("(lambda x)")
    scene = Scene()
    scene.add(src)
    anim = CodeTransform(src, dst, [(["let"], ["lambda"])])
    anim._setup_scene(scene)
    scene.add_mobjects_from_animations([anim])
    anim.begin()
    anim.interpolate(1.0)
    anim.finish()
    anim.clean_up_from_scene(scene)
    assert scene.mobjects == [dst]


def test_other_mobjects_in_the_scene_survive():
    from manim import Dot

    src, dst = Code("(a + b)"), Code("(+ a b)")
    bystander = Dot()
    scene = Scene()
    scene.add(bystander, src)
    anim = CodeTransform(src, dst)
    anim._setup_scene(scene)
    scene.add_mobjects_from_animations([anim])
    anim.begin()
    anim.interpolate(1.0)
    anim.finish()
    anim.clean_up_from_scene(scene)
    assert scene.mobjects == [bystander, dst]


# --- clone and merge -------------------------------------------------------


def test_clone_moves_the_original_and_copies_the_rest():
    """The original must travel to one destination, not stay put.

    Sending copies to *every* destination leaves the source glyph sitting at
    its old position for the whole animation and blinking out at the end —
    three `a`s on screen for a split that should produce two.
    """
    from manim import ReplacementTransform, TransformFromCopy

    src, dst = Code("(swap a b)"), Code("(let (t a) (set a b))")
    anim = CodeTransform(src, dst, [(["a"], dst.all("a"))], lag=0)
    flat = _flatten(anim)

    source_glyph = src.group(src.nth("a"))[0]
    consumed = [
        a for a in flat
        if isinstance(a, ReplacementTransform) and a.mobject is source_glyph
    ]
    assert len(consumed) == 1, "the original has to go somewhere"
    assert sum(isinstance(a, TransformFromCopy) for a in flat) == 1


def test_a_clone_animates_one_thing_per_destination():
    src, dst = Code("(swap a b)"), Code("(let (t a) (set a b) (f a))")
    anim = CodeTransform(src, dst, [(["a"], dst.all("a"))], lag=0)
    clone = next(c for c in anim.correspondences if c.op is Op.CLONE)
    assert len(clone.dst) == 3
    # one mover + two copies, never a stationary leftover
    from manim import ReplacementTransform, TransformFromCopy

    flat = _flatten(anim)
    movers = sum(
        isinstance(a, (ReplacementTransform, TransformFromCopy)) for a in flat
    )
    assert movers >= 3


def test_clone_is_staggered_by_default():
    from manim import LaggedStart

    src, dst = Code("(swap a b)"), Code("(let (t a) (set a b))")
    anim = CodeTransform(src, dst, [(["a"], dst.all("a"))])
    assert any(isinstance(a, LaggedStart) for a in anim.animations)


def test_clone_of_a_whole_subexpression():
    src = Code("(g (h x))")
    dst = Code("((h x) (h x))")
    anim = CodeTransform(src, dst, [([src.nth("(h x)")], dst.all("(h x)"))], lag=0)
    clone = next(c for c in anim.correspondences if c.op is Op.CLONE)
    # one group in, two groups out, four tokens each
    assert len(clone.src) == 1 and len(clone.dst) == 2
    assert all(len(g) == 4 for g in clone.dst)


def test_merge_keeps_one_and_dissolves_the_rest():
    from manim import FadeTransform

    src, dst = Code("(f tmp tmp)"), Code("(f tmp)")
    anim = CodeTransform(src, dst, [(src.all("tmp"), ["tmp"])])
    flat = _flatten(anim)
    assert sum(isinstance(a, FadeTransform) for a in flat) == 1


def test_clone_and_merge_leave_the_scene_clean():
    for before, after, mapping_for in [
        ("(swap a b)", "(let (t a) (set a b))", lambda s, d: [(["a"], d.all("a"))]),
        ("(f tmp tmp)", "(f tmp)", lambda s, d: [(s.all("tmp"), ["tmp"])]),
    ]:
        src, dst = Code(before), Code(after)
        scene = Scene()
        scene.add(src)
        anim = CodeTransform(src, dst, mapping_for(src, dst))
        anim._setup_scene(scene)
        scene.add_mobjects_from_animations([anim])
        anim.begin()
        anim.interpolate(1.0)
        anim.finish()
        anim.clean_up_from_scene(scene)
        assert scene.mobjects == [dst], f"{before} -> {after}"


def _flatten(animation):
    out = []
    for a in getattr(animation, "animations", []):
        out.append(a)
        out.extend(_flatten(a))
    return out
