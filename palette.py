"""Color math for building and checking a theme.

Everything here is a pure function of hex strings. No manim, no server, no
`Theme` — `theme.py` and the editor both call in, neither is imported back.

Two ideas carry the module.

**Work in OKLCH.** HSL's "lightness" is not perceptual: `#1aff47` and
`#0000ff` are both L=50% and one is blinding beside the other. That is why
picking a palette by hand turns into hunting a lightness per color — the
number does not mean the same thing at each hue. In OKLCH a single L reads as
one brightness across the wheel, so a palette can be specified as "these four
hues, this lightness, this chroma" and come out even.

**Contrast and separation are different questions.** Contrast is against the
background and decides legibility. Separation is between two token colors and
decides whether you can tell a comment from a keyword. A color can pass one
and fail the other, which is exactly how a comment ends up the same teal as
the keyword next to it on a teal background.
"""

from __future__ import annotations

import math
from itertools import permutations

Hex = str

# --- hex, sRGB, linear ------------------------------------------------------


def _to_rgb(hex_color: Hex) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _to_hex(rgb: tuple[float, float, float]) -> Hex:
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, round(c * 255))) for c in rgb
    )


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gamma(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


# --- OKLCH ------------------------------------------------------------------


def to_oklch(hex_color: Hex) -> tuple[float, float, float]:
    """(lightness 0-1, chroma, hue in degrees)."""
    r, g, b = (_linear(c) for c in _to_rgb(hex_color))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    lightness = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_ = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return lightness, math.hypot(a, b_), math.degrees(math.atan2(b_, a)) % 360


def from_oklch(lightness: float, chroma: float, hue: float) -> Hex:
    """The nearest in-gamut sRGB color, found by reducing chroma.

    A hue and lightness can name a color sRGB cannot show — vivid yellows and
    cyans especially. Clipping the channels there shifts the hue visibly, so
    chroma is walked down until the color fits and the hue survives.
    """
    for step in range(64):
        c = chroma * (1 - step / 64)
        a_, b_ = c * math.cos(math.radians(hue)), c * math.sin(math.radians(hue))
        l_ = lightness + 0.3963377774 * a_ + 0.2158037573 * b_
        m_ = lightness - 0.1055613458 * a_ - 0.0638541728 * b_
        s_ = lightness - 0.0894841775 * a_ - 1.2914855480 * b_
        l, m, s = (v**3 for v in (l_, m_, s_))
        rgb = (
            +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
        )
        if all(-0.001 <= v <= 1.001 for v in rgb):
            return _to_hex(tuple(_gamma(max(0.0, min(1.0, v))) for v in rgb))
    return _to_hex(tuple(_gamma(max(0.0, min(1.0, v))) for v in rgb))


# --- measuring --------------------------------------------------------------


def luminance(hex_color: Hex) -> float:
    r, g, b = (_linear(c) for c in _to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: Hex, b: Hex) -> float:
    """WCAG contrast ratio, 1.0 to 21.0."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


LIGHTNESS_ENOUGH = 0.20
"""One is clearly lighter than the other."""
CHROMA_ENOUGH = 0.06
"""One is clearly more colorful than the other."""
HUE_ENOUGH = 45.0
"""They are clearly different colors — only meaningful if both have a color."""
CHROMATIC = 0.04
"""Below this a color is grey enough that its hue is not perceptible."""


def separation(a: Hex, b: Hex) -> float:
    """How distinguishable two colors are as text. 1.0 is the threshold.

    Three independent ways colors differ, scored separately, best one wins.
    Any single distance metric fails here, as these real cases show:

        pair                          ΔL     Δchroma   Δhue    verdict
        one-dark identifier/builtin   0.039  0.071     56.7    fine
        marine keyword/builtin        0.076  0.011     34.4    indistinguishable
        teal comment/teal keyword     0.148  0.046      2.2    indistinguishable
        dim teal/teal keyword         0.267  0.048      0.3    fine
        near-white/cyan               0.069  0.095     66.5    fine

    Note rows one and two: nearly identical chroma *distance* in OKLab, and
    opposite verdicts. Averaging the axes — a euclidean distance — cannot tell
    them apart, because what makes one/builtin readable is that a near-grey
    and a cyan differ in how colorful they are, while marine's two teals are
    equally colorful and merely a few degrees apart in hue.

    Hue only counts when both colors have enough chroma to show one. Two greys
    can be 180 degrees apart in nominal hue and look identical.

    Contrast says nothing about any of this: two colors can both clear 7:1
    against the background and be the same color as each other.
    """
    la, ca, ha = to_oklch(a)
    lb, cb, hb = to_oklch(b)
    scores = [abs(la - lb) / LIGHTNESS_ENOUGH, abs(ca - cb) / CHROMA_ENOUGH]
    if min(ca, cb) >= CHROMATIC:
        scores.append(hue_gap(ha, hb) / HUE_ENOUGH)
    return max(scores)


def hue_gap(a: float, b: float) -> float:
    """Degrees between two hues, the short way round."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def lift_to_contrast(
    background: Hex, hue: float, chroma: float, lightness: float, target: float
) -> Hex:
    """That hue and chroma, made lighter only as far as the target needs.

    Raising lightness rather than picking one: the same color needs a very
    different lightness on `#0e0f16` than on `#22253a`, and letting the
    requirement decide is what stops a palette from having to be re-tuned by
    hand for every background.
    """
    best = from_oklch(lightness, chroma, hue)
    while lightness < 0.99 and contrast(background, best) < target:
        lightness += 0.01
        best = from_oklch(lightness, chroma, hue)
    return best


# --- generating -------------------------------------------------------------

# Where each role sits on the wheel in the palette the video started from, so
# a generated palette can keep the conventions — purple-ish keywords, cyan
# builtins, warm literals, green strings — whenever the background allows.
CANONICAL_HUES = {  # measured off One Dark's own colors
    "keyword": 318.0,  # purple
    "builtin": 206.0,  # cyan
    "literal": 64.0,  # orange
    "string": 133.0,  # green
}

# Relative to the palette's chroma, so one knob moves the whole thing. A bare
# number has no shape to recognize it by, so literals get the most; strings
# and keywords sit just under.
ROLE_CHROMA = {"keyword": 1.0, "builtin": 0.92, "literal": 1.05, "string": 0.98}

# Perceptual lightness per role, which in OKLCH really does read the same
# across hues — this is the whole reason for working here rather than in HSL.
ROLE_LIGHTNESS = {"keyword": 0.75, "builtin": 0.78, "literal": 0.82, "string": 0.80}

CHROMA = 0.15  # how vivid a generated palette is, before per-role weighting

SPREAD = 185.0
"""How much of the wheel the four accents occupy.

Wide enough that adjacent roles stay apart. At 135 a dark green background put
`literal` and `string` 0.090 apart — a pink and a peach, near enough to read
as one color; at 185 the same background gives 0.136. Narrower is prettier and
more likely to produce two accents you cannot tell apart.
"""

# Hues that read as a warning wherever they land.
ALARM_RED, ALARM_PINK, ALARM_ORANGE = 17.0, 358.0, 55.0

ACCENT_FLOOR = 4.5
IDENTIFIER_TARGET = 8.0
COMMENT_TARGET = 4.6


NEUTRAL_CHROMA = 0.04
"""Below this the background has no hue worth avoiding.

`#0e0f16` computes to hue 278, but that number falls out of a couple of units
of difference between channels in a color that is nearly black. Treating it as
a constraint pushes all four accents into the arc opposite a hue nobody can
see, which is how a near-black background ends up unable to have a purple
keyword.
"""


def accent_hues(
    background: Hex, spread: float = SPREAD, offset: float = 0.0
) -> dict[str, float]:
    """Four hues for the four accent roles, placed against the background.

    A saturated background gets the accents spread evenly across an arc on the
    far side of the wheel, so nothing lands on its hue and goes flat against
    it. A neutral one imposes nothing, so the canonical hues are used as they
    are — which is what makes a near-black theme able to look like One Dark
    and a teal one unable to, correctly.

    Roles are assigned to hues by whichever of the 24 arrangements stays
    closest to the canonical ones. Rotating the family as a unit instead — the
    obvious shortcut — gives palettes with a cyan keyword and an olive
    builtin: technically a palette, reads as noise.
    """
    _, chroma, background_hue = to_oklch(background)
    if chroma < NEUTRAL_CHROMA:
        return {role: (hue + offset) % 360 for role, hue in CANONICAL_HUES.items()}

    centre = background_hue + 180 + offset
    hues = [centre - spread / 2 + spread * i / 3 for i in range(4)]

    roles = list(CANONICAL_HUES)
    best, best_cost = None, None
    for order in permutations(roles):
        cost = sum(hue_gap(CANONICAL_HUES[r], h) for r, h in zip(order, hues))
        if best_cost is None or cost < best_cost:
            best, best_cost = order, cost
    return {role: hue % 360 for role, hue in zip(best, hues)}


def generate_identifier(background: Hex) -> Hex:
    """Near-white, carrying a little of the background's hue."""
    _, _, hue = to_oklch(background)
    return lift_to_contrast(background, hue, 0.03, 0.88, IDENTIFIER_TARGET)


def generate_comment(background: Hex) -> Hex:
    """The quietest thing that is still readable, in the background's hue."""
    _, _, hue = to_oklch(background)
    return lift_to_contrast(background, hue, 0.05, 0.45, COMMENT_TARGET)


def generate_accent(background: Hex, role: str, **kwargs) -> Hex:
    """One accent role, placed as the full palette would place it."""
    hue = accent_hues(background, **kwargs)[role]
    chroma = CHROMA * ROLE_CHROMA[role]
    return lift_to_contrast(
        background, hue, chroma, ROLE_LIGHTNESS[role], ACCENT_FLOOR
    )


def generate_keyword(background: Hex) -> Hex:
    return generate_accent(background, "keyword")


def generate_palette(
    background: Hex,
    spread: float = SPREAD,
    offset: float = 0.0,
    chroma: float = CHROMA,
) -> dict[str, Hex]:
    """Every token color for a background: the whole palette in one call."""
    hues = accent_hues(background, spread, offset)
    colors = {}
    for role, hue in hues.items():
        colors[role] = lift_to_contrast(
            background,
            hue,
            chroma * ROLE_CHROMA[role],
            ROLE_LIGHTNESS[role],
            ACCENT_FLOOR,
        )
    identifier = generate_identifier(background)
    colors["identifier"] = identifier
    colors["delimiter"] = identifier
    colors["punctuation"] = identifier
    colors["operator"] = colors["keyword"]
    colors["comment"] = generate_comment(background)
    return colors


def generate_chrome(background: Hex, identifier: Hex) -> dict[str, Hex]:
    """Surfaces, frames and quiet text for a background.

    The surfaces are the background's own hue lifted in lightness rather than
    mixed toward the foreground. Mixing works on a near-black ground and falls
    apart as the background saturates — the panels go gray and stop belonging
    to the palette. `muted` and `subtle` are lifted to a contrast target for
    the same reason the accents are: on a light background the mix leaves
    captions at around 3:1, which is under what is readable.
    """
    lightness, chroma, hue = to_oklch(background)
    return {
        "surface": from_oklch(lightness + 0.05, chroma * 0.9, hue),
        "surface_stroke": from_oklch(lightness + 0.16, chroma * 0.7, hue),
        "frame": from_oklch(lightness + 0.03, chroma * 0.95, hue),
        "frame_stroke": from_oklch(lightness + 0.20, chroma * 0.65, hue),
        "muted": lift_to_contrast(background, hue, 0.04, 0.60, 6.0),
        "subtle": lift_to_contrast(background, hue, 0.035, 0.55, 4.5),
        "danger": _danger_for(background),
    }


def _danger_for(background: Hex) -> Hex:
    """Red, else hot pink, else orange-red.

    Stays in the alarm band whatever the background is. Derived from the
    background like everything else, a red ground would give a green "bad
    option" marker, which contrasts beautifully and means nothing.
    """
    _, _, hue = to_oklch(background)
    choices = (ALARM_RED, ALARM_PINK, ALARM_ORANGE)
    clear = [h for h in choices if hue_gap(h, hue) >= 40]
    # Red first when it is available, because it is the one that reads as a
    # warning without being explained. When the background is itself red or
    # orange nothing in the band clears, and the answer is whichever is
    # furthest from it — falling back to the first would put a red marker on a
    # red field, which is the failure this function exists to avoid.
    choice = clear[0] if clear else max(choices, key=lambda h: hue_gap(h, hue))
    return lift_to_contrast(background, choice, 0.16, 0.70, 5.5)


# --- color blindness --------------------------------------------------------

# Brettel/Viénot-style approximations, applied in linear sRGB.
_CVD = {
    "protanopia": ((0.170, 0.829, 0.0), (0.170, 0.829, 0.0), (-0.004, 0.024, 0.980)),
    "deuteranopia": ((0.330, 0.670, 0.0), (0.330, 0.670, 0.0), (-0.028, 0.125, 0.903)),
    "tritanopia": ((1.255, -0.077, -0.178), (-0.078, 0.931, 0.148), (0.005, 0.691, 0.304)),
}


def simulate(hex_color: Hex, kind: str) -> Hex:
    """What a color looks like to someone with that form of color blindness."""
    matrix = _CVD[kind]
    r, g, b = (_linear(c) for c in _to_rgb(hex_color))
    out = tuple(sum(m * v for m, v in zip(row, (r, g, b))) for row in matrix)
    return _to_hex(tuple(_gamma(max(0.0, min(1.0, v))) for v in out))
