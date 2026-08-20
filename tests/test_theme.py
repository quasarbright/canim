import json

import pytest

from canim import theme
from canim.lexer import Kind


def a_theme(**overrides):
    base = dict(
        name="test",
        background="#101020",
        colors={kind: "#abcdef" for kind in Kind},
    )
    return theme.Theme(**{**base, **overrides})


# --- deriving ---------------------------------------------------------------


def test_unpinned_chrome_is_derived_from_the_background():
    t = a_theme()
    assert t.surface == theme._mix("#101020", "#abcdef", 0.06)
    assert t.danger == theme.DEFAULT_DANGER


def test_pinned_chrome_is_left_alone():
    assert a_theme(surface="#123456").surface == "#123456"


def test_pinned_records_only_what_was_named():
    t = a_theme(surface="#123456", danger="#ff0000")
    assert t.pinned == {"surface", "danger"}
    assert a_theme().pinned == frozenset()


# --- the file format --------------------------------------------------------


def test_written_form_is_flat():
    data = theme.to_dict(a_theme(muted="#334455"))
    assert data["name"] == "test"
    assert data["keyword"] == "#abcdef"  # not nested under `colors`
    assert data["chrome_muted"] == "#334455"


def test_derived_chrome_is_not_written():
    # Writing it back would freeze a value that is supposed to follow the
    # background — a later edit to the background would silently stop
    # reaching it.
    data = theme.to_dict(a_theme(muted="#334455"))
    assert "chrome_muted" in data
    assert "chrome_surface" not in data


def test_round_trip_preserves_colors_and_pinning():
    t = a_theme(surface="#123456", danger="#ff0000")
    back = theme.from_dict(json.loads(json.dumps(theme.to_dict(t))))
    assert back.background == t.background
    assert all(back.colors[k] == t.colors[k] for k in Kind)
    assert all(getattr(back, f) == getattr(t, f) for f in theme.CHROME_FIELDS)
    assert back.pinned == t.pinned


@pytest.mark.parametrize("name", theme.discover())
def test_every_shipped_theme_round_trips(name):
    t = theme.open(name)
    back = theme.from_dict(theme.to_dict(t))
    assert all(back.colors[k] == t.colors[k] for k in Kind)
    assert all(getattr(back, f) == getattr(t, f) for f in theme.CHROME_FIELDS)


def test_every_shipped_theme_names_every_kind():
    for name in theme.discover():
        assert set(theme.open(name).colors) == set(Kind), name


# --- paths ------------------------------------------------------------------


def test_a_bare_name_means_one_of_canims_own():
    assert theme.path_for("marine") == theme.THEMES_DIR / "marine.theme.json"


def test_a_path_is_left_as_given(tmp_path):
    assert theme.path_for(tmp_path / "x.theme.json") == tmp_path / "x.theme.json"


def test_saving_somewhere_else_works(tmp_path):
    path = theme.save(a_theme(), tmp_path / "mine.theme.json")
    assert theme.open(path).background == "#101020"


def test_saving_refuses_a_file_that_is_not_a_theme(tmp_path):
    with pytest.raises(ValueError, match="must end in"):
        theme.save(a_theme(), tmp_path / "mine.json")


# --- malformed input --------------------------------------------------------


def test_a_short_hex_is_refused_by_name():
    data = theme.to_dict(a_theme())
    data["keyword"] = "#eee"
    with pytest.raises(ValueError, match="keyword must be a 6-digit hex"):
        theme.from_dict(data)


def test_a_missing_colour_is_refused_by_name():
    data = theme.to_dict(a_theme())
    del data["string"]
    with pytest.raises(ValueError, match="no color for 'string'"):
        theme.from_dict(data)


def test_hex_case_is_normalised():
    data = theme.to_dict(a_theme())
    data["keyword"] = "#AABBCC"
    assert theme.from_dict(data).colors[Kind.KEYWORD] == "#aabbcc"
