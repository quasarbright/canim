"""Turning a correspondence into manim animations.

Glyph pairing is done here rather than handed to manim. ``Transform`` on two
VGroups calls ``align_data``, which pads the shorter side by duplicating
submobjects — that renders as a smear. Since the correspondence is already
known exactly, pair explicitly and let a length mismatch degrade to a fade.
"""

from __future__ import annotations

from manim import (
    Animation,
    AnimationGroup,
    FadeIn,
    FadeOut,
    FadeTransform,
    LaggedStart,
    ReplacementTransform,
    TransformFromCopy,
    Scene,
    VGroup,
)

from .code import Code
from .matcher import Correspondence, Op, match
from .refs import resolve_mapping


class CodeTransform(AnimationGroup):
    """Animate ``source`` into ``dest``.

    The scene should hold ``source`` beforehand and will hold ``dest`` after.
    """

    def __init__(
        self,
        source: Code,
        dest: Code,
        mapping=(),
        *,
        path_arc: float = 0.0,
        lag: float = 0.08,
        **kwargs,
    ):
        self.source = source
        self.dest = dest
        entries = resolve_mapping(mapping, source, dest)
        self.correspondences = match(source.tokens, dest.tokens, entries)

        animations: list[Animation] = []
        for correspondence in self.correspondences:
            animations.extend(
                _animations(
                    correspondence, source, dest, path_arc=path_arc, lag=lag
                )
            )
        super().__init__(*animations, **kwargs)
        # Captured before manim gets a chance to restructure it.
        self._source_family = list(source.get_family())

    def clean_up_from_scene(self, scene: Scene) -> None:
        """Leave the scene holding `dest` and nothing of `source`.

        Manim tears `source` apart before we ever run: `Scene.add` restructures
        the scene so nothing is drawn twice, and since our animations target
        glyphs living *inside* `source`, adding the animation group extracts
        them and scatters the remainder as loose top-level mobjects. Padding
        from `align_data` lands there too. None of it is visible, but it would
        pile up over a scene's worth of beats, so it goes by family.
        """
        super().clean_up_from_scene(scene)
        stale = {id(m) for m in self._source_family}
        stale |= {id(m) for m in self.mobject.get_family()}
        stale |= {id(m) for m in self.dest.get_family()}
        # The glyph slices themselves: new VGroups wrapping dest's children, so
        # they aren't caught by dest's family, but leaving them in the scene
        # draws those glyphs twice.
        for animation in self.animations:
            # `mobject` covers most of it; `target_mobject` covers Transform;
            # `to_add_on_completion` covers FadeTransform, which puts a third
            # mobject into the scene that neither of the others names.
            for attr in ("mobject", "target_mobject", "to_add_on_completion"):
                leftover = getattr(animation, attr, None)
                if leftover is not None:
                    stale.add(id(leftover))
        scene.mobjects = [
            m for m in scene.mobjects if id(m) not in stale
        ] + [self.dest]


def _animations(
    correspondence: Correspondence,
    source: Code,
    dest: Code,
    *,
    path_arc: float,
    lag: float = 0.0,
) -> list[Animation]:
    op = correspondence.op

    if op is Op.MOVE:
        return _pair(
            source.group(correspondence.src_tokens),
            dest.group(correspondence.dst_tokens),
            path_arc=path_arc,
        )
    if op is Op.MORPH:
        return _morph(
            source.group(correspondence.src_tokens),
            dest.group(correspondence.dst_tokens),
            _text(source, correspondence.src_tokens),
            _text(dest, correspondence.dst_tokens),
            path_arc=path_arc,
        )
    if op is Op.CLONE:
        return _clone(correspondence, source, dest, path_arc=path_arc, lag=lag)
    if op is Op.MERGE:
        return _merge(correspondence, source, dest, path_arc=path_arc)
    if op is Op.FADE_OUT:
        return [FadeOut(source.group(correspondence.src_tokens))]
    if op is Op.FADE_IN:
        return [FadeIn(dest.group(correspondence.dst_tokens))]

    raise NotImplementedError(f"{op.value} has no animation")


def _clone(correspondence, source, dest, *, path_arc, lag) -> list[Animation]:
    """One group becoming several.

    The original *travels* to the first destination and copies peel off to the
    rest, which is what duplication looks like. Sending copies to every
    destination instead leaves the original sitting at its old position for the
    whole animation and blinking out at the end — three `a`s on screen for a
    split that should produce two.

    Departures are staggered so a split reads as a split rather than as one
    object smearing in several directions.
    """
    src = source.group(correspondence.src[0])
    first, *rest = correspondence.dst

    parts = [AnimationGroup(*_pair(src, dest.group(first), path_arc=path_arc))]
    # Safe to read `src` after the line above: Transform.begin copies its
    # target, so the copies capture the original's appearance before anything
    # animates.
    parts += [
        AnimationGroup(*_pair_from_copy(src, dest.group(group), path_arc=path_arc))
        for group in rest
    ]

    if lag and len(parts) > 1:
        return [LaggedStart(*parts, lag_ratio=lag)]
    return parts


def _merge(correspondence, source, dest, *, path_arc) -> list[Animation]:
    """Several groups converging on one.

    The first arrives and stays; the rest travel to the same slot and dissolve
    into it as they land, so the collapse is visible rather than one of them
    simply vanishing early.
    """
    target = dest.group(correspondence.dst[0])
    keep, *rest = correspondence.src
    animations = _pair(source.group(keep), target, path_arc=path_arc)
    for group in rest:
        animations.append(
            FadeTransform(source.group(group), target.copy())
        )
    return animations


def _pair_from_copy(src: VGroup, dst: VGroup, **kwargs) -> list[Animation]:
    """Like `_pair`, but the source stays put and copies do the travelling."""
    shared = min(len(src), len(dst))
    return [
        *[TransformFromCopy(src[i], dst[i], **kwargs) for i in range(shared)],
        *[FadeIn(m) for m in dst[shared:]],
    ]


def _text(code: Code, indices) -> str:
    return "".join(code.tokens[i].text for i in indices)


def _morph(src: VGroup, dst: VGroup, before: str, after: str, **kwargs) -> list[Animation]:
    """One thing becoming different text.

    When the two spellings share a real prefix — `tmp` into `tmp_G4271` — pair
    glyph by glyph so the shared part holds still and the rest grows out of it.
    When they don't, glyph pairing produces `e`->`a`, `t`->`m` in place, which
    reads as mush; cross-fade the whole thing instead.
    """
    shared = 0
    for a, b in zip(before, after):
        if a != b:
            break
        shared += 1
    if shared >= 2 and shared >= 0.4 * min(len(before), len(after)):
        return _pair(src, dst, **kwargs)
    return [FadeTransform(src, dst)]


def _pair(src: VGroup, dst: VGroup, **kwargs) -> list[Animation]:
    """Positional glyph pairing. Extras on either side fade rather than smear."""
    shared = min(len(src), len(dst))
    return [
        *[ReplacementTransform(src[i], dst[i], **kwargs) for i in range(shared)],
        *[FadeOut(m) for m in src[shared:]],
        *[FadeIn(m) for m in dst[shared:]],
    ]
