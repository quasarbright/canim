import pytest

from canim import palette as P
from canim.lexer import Kind

BACKGROUNDS = ["#0e0f16", "#22253a", "#08004d", "#022c26", "#510606", "#022210"]


# --- OKLCH ------------------------------------------------------------------


@pytest.mark.parametrize("color", ["#000000", "#ffffff", "#c678dd", "#08004d", "#1aff47"])
def test_oklch_round_trips(color):
    assert P.from_oklch(*P.to_oklch(color)) == color


def test_lightness_is_perceptual():
    # The reason for working in OKLCH at all: in HSL these two are both "50%
    # lightness" and one is far brighter than the other.
    green = P.to_oklch("#1aff47")[0]
    blue = P.to_oklch("#0000ff")[0]
    assert green > blue + 0.3


def test_out_of_gamut_keeps_its_hue():
    # A vivid yellow at high chroma is not in sRGB. Clipping channels would
    # swing the hue; reducing chroma keeps it.
    asked = 100.0
    got = P.to_oklch(P.from_oklch(0.9, 0.4, asked))[2]
    assert P.hue_gap(asked, got) < 5


# --- measuring --------------------------------------------------------------


def test_contrast_extremes():
    assert P.contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert P.contrast("#888888", "#888888") == pytest.approx(1.0)


def test_separation_is_zero_for_a_color_and_itself():
    assert P.separation("#c678dd", "#c678dd") == pytest.approx(0.0)


def test_any_one_kind_of_difference_is_enough_on_its_own():
    assert P.separation("#186d61", "#28c8b3") > 1.0  # lightness carries it
    assert P.separation("#e0e0f0", "#66ddff") > 1.0  # chroma carries it
    assert P.separation("#e08a5a", "#5a9be0") > 1.0  # hue carries it


def test_a_near_grey_beside_a_colour_is_distinguishable():
    # One Dark's identifier and builtin. Their chroma *distance* matches
    # marine's two teals almost exactly, and the verdicts are opposite: what
    # separates these is that one is nearly grey and the other is not.
    assert P.separation("#abb2bf", "#56b6c2") > 1.0


def test_two_colours_of_the_same_hue_and_chroma_are_not():
    assert P.separation("#28c8b3", "#2edcff") < 1.0


def test_hue_is_ignored_when_neither_colour_has_any():
    # Two near-greys can be far apart in nominal hue and look identical, so
    # hue must not rescue them.
    assert P.separation("#7f7f80", "#807f7f") < 1.0


def test_separation_catches_what_contrast_misses():
    # Picking a comment for marine's teal background by contrast alone gave
    # #3f9186, which clears 4.6:1 and is visibly the keyword's colour. The one
    # that got used, #186d61, is dimmer *and* further away. Contrast cannot
    # tell those two apart; separation can.
    background, keyword = "#022c26", "#28c8b3"
    picked_by_contrast, picked_by_eye = "#3f9186", "#186d61"

    # Contrast prefers the wrong one — it is the brighter of the two.
    assert P.contrast(background, picked_by_contrast) > P.contrast(
        background, picked_by_eye
    )
    # Separation prefers the right one.
    assert P.separation(picked_by_contrast, keyword) < 1.0
    assert P.separation(picked_by_eye, keyword) > 1.0


def test_lift_reaches_the_target_and_stops():
    background = "#22253a"
    color = P.lift_to_contrast(background, 200.0, 0.1, 0.2, 7.0)
    assert P.contrast(background, color) >= 7.0


# --- generating -------------------------------------------------------------


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_a_generated_palette_names_every_kind(background):
    assert set(P.generate_palette(background)) == {k.value for k in Kind}


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_every_generated_color_is_readable(background):
    palette = P.generate_palette(background)
    for role, color in palette.items():
        assert P.contrast(background, color) >= 4.4, f"{role} on {background}"


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_generated_roles_are_distinguishable(background):
    palette = P.generate_palette(background)
    roles = ["keyword", "builtin", "literal", "string", "comment", "identifier"]
    for i, a in enumerate(roles):
        for b in roles[i + 1 :]:
            assert P.separation(palette[a], palette[b]) > 1.0, f"{a} vs {b}"


def test_a_neutral_background_gets_the_canonical_hues():
    # Nothing to avoid, so a near-black theme can look like One Dark.
    hues = P.accent_hues("#0e0f16")
    for role, canonical in P.CANONICAL_HUES.items():
        assert P.hue_gap(hues[role], canonical) < 1


@pytest.mark.parametrize("background", ["#08004d", "#510606", "#022210"])
def test_a_saturated_background_pushes_accents_off_its_own_hue(background):
    _, _, background_hue = P.to_oklch(background)
    for hue in P.accent_hues(background).values():
        assert P.hue_gap(hue, background_hue) > 40


def test_offset_rotates_without_changing_the_shape():
    a = P.accent_hues("#08004d", offset=0)
    b = P.accent_hues("#08004d", offset=40)
    assert a != b
    assert sorted(P.hue_gap(a[r], b[r]) for r in a) == pytest.approx([40] * 4, abs=1)


def test_chroma_controls_vividness():
    quiet = P.generate_palette("#08004d", chroma=0.05)["string"]
    loud = P.generate_palette("#08004d", chroma=0.20)["string"]
    assert P.to_oklch(loud)[1] > P.to_oklch(quiet)[1]


# --- chrome -----------------------------------------------------------------


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_surfaces_sit_above_the_background(background):
    chrome = P.generate_chrome(background, P.generate_identifier(background))
    for field in ("surface", "surface_stroke", "frame", "frame_stroke"):
        assert P.to_oklch(chrome[field])[0] > P.to_oklch(background)[0]


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_quiet_text_stays_readable(background):
    chrome = P.generate_chrome(background, P.generate_identifier(background))
    assert P.contrast(background, chrome["muted"]) >= 5.9
    assert P.contrast(background, chrome["subtle"]) >= 4.4


@pytest.mark.parametrize("background", ["#510606", "#022210", "#08004d"])
def test_danger_stays_in_the_alarm_band(background):
    danger = P.generate_chrome(background, "#ffffff")["danger"]
    _, _, hue = P.to_oklch(danger)
    assert min(P.hue_gap(hue, h) for h in (P.ALARM_RED, P.ALARM_PINK, P.ALARM_ORANGE)) < 20


def test_danger_gets_as_far_from_a_red_background_as_the_band_allows():
    # On a red ground no alarm hue clears the usual floor, so the answer is
    # whichever is furthest. Falling back to the first of the list instead
    # would put a red marker on a red field.
    background = "#510606"
    _, _, background_hue = P.to_oklch(background)
    _, _, hue = P.to_oklch(P.generate_chrome(background, "#ffffff")["danger"])
    furthest = max(
        P.hue_gap(h, background_hue)
        for h in (P.ALARM_RED, P.ALARM_PINK, P.ALARM_ORANGE)
    )
    assert P.hue_gap(hue, background_hue) == pytest.approx(furthest, abs=1)


# --- colour blindness -------------------------------------------------------


@pytest.mark.parametrize("kind", ["protanopia", "deuteranopia", "tritanopia"])
def test_simulation_returns_a_colour(kind):
    assert P.simulate("#c678dd", kind).startswith("#")
    assert len(P.simulate("#c678dd", kind)) == 7


def test_deuteranopia_pulls_red_and_green_together():
    before = P.separation("#ff0000", "#00ff00")
    after = P.separation(
        P.simulate("#ff0000", "deuteranopia"), P.simulate("#00ff00", "deuteranopia")
    )
    assert after < before
