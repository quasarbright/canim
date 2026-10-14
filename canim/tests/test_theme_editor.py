"""The two functions in the editor's server that do real work.

The routing is thin enough to read; these are the parts that would be wrong
without anyone noticing.
"""

import pytest

from canim import theme
from canim.theme_editor.server import (
    analyze, create_theme, filename_for, segments, unused_name,
)


def a_theme(**overrides):
    base = {
        "name": "t",
        "background": "#101020",
        "identifier": "#e0e0f0",
        "keyword": "#ff88cc",
        "builtin": "#66ddff",
        "operator": "#ff88cc",
        "literal": "#ffcc66",
        "delimiter": "#e0e0f0",
        "punctuation": "#e0e0f0",
        "string": "#88ee99",
        "comment": "#8a8aa8",
    }
    return {**base, **overrides}


# --- lexing -----------------------------------------------------------------


def test_segments_cover_every_character():
    source = "(let ((x 1))\n  x)"
    assert "".join(s["text"] for s in segments(source, "lisp")) == source


def test_whitespace_carries_no_kind():
    kinds = {s["kind"] for s in segments("(f x)", "lisp") if s["text"].isspace()}
    assert kinds == {None}


def test_kinds_come_from_the_real_lexer():
    by_text = {s["text"]: s["kind"] for s in segments("(defmacro f)", "lisp")}
    assert by_text["defmacro"] == "builtin"


# --- analysis ---------------------------------------------------------------


def test_faint_text_is_flagged():
    result = analyze(a_theme(comment="#16161f"))
    assert any("too faint" in m for m in result["warnings"]["comment"])


def test_merely_low_contrast_is_a_softer_flag():
    result = analyze(a_theme(comment="#6f6f92"))
    messages = result["warnings"]["comment"]
    assert any("under 4.5:1" in m for m in messages)
    assert not any("too faint" in m for m in messages)


def test_colliding_roles_are_flagged_on_both_sides():
    result = analyze(a_theme(keyword="#6ad9fb", operator="#6ad9fb"))
    assert any("builtin" in m for m in result["warnings"]["keyword"])
    assert any("keyword" in m for m in result["warnings"]["builtin"])


def test_sharing_a_color_on_purpose_is_not_a_collision():
    # Operators take the keyword's color by convention, and delimiters take
    # the identifier's. Reporting those would flag every theme in the repo.
    result = analyze(a_theme())
    assert "operator" not in result["warnings"]
    assert "delimiter" not in result["warnings"]


def test_an_accidental_match_is_still_a_collision():
    # Only the conventional pairs get a pass. A keyword that happens to equal
    # the builtin is a real problem, and checking for identical hexes rather
    # than for the specific pairs would wave it through.
    result = analyze(a_theme(keyword="#66ddff", operator="#66ddff"))
    assert "keyword" in result["warnings"]


def test_a_clean_theme_has_nothing_to_say():
    assert analyze(a_theme())["warnings"] == {}


def test_chrome_text_is_checked_when_present():
    result = analyze(a_theme(chrome_muted="#1a1a26"))
    assert "chrome_muted" in result["warnings"]


def test_derived_chrome_is_not_checked():
    # It is not in the file, so there is nothing to warn about — the value
    # follows the background by construction.
    assert "chrome_muted" not in analyze(a_theme())["contrast"]


# --- new themes -------------------------------------------------------------


def test_filenames_follow_the_existing_ones():
    assert filename_for("tree frog") == "tree-frog.theme.json"
    assert filename_for("  a/b  c ") == "a-b-c.theme.json"


def test_a_theme_needs_a_name():
    with pytest.raises(ValueError):
        filename_for("   ")


def test_create_writes_a_new_file(tmp_path):
    path = tmp_path / "dusk.theme.json"
    created = create_theme(a_theme(name="dusk"), path)
    assert theme.open(path).name == "dusk"
    assert created["background"] == "#101020"


def test_create_never_overwrites(tmp_path):
    path = tmp_path / "dusk.theme.json"
    create_theme(a_theme(name="dusk"), path)
    with pytest.raises(ValueError, match="already"):
        create_theme(a_theme(name="dusk", background="#000000"), path)
    assert theme.open(path).background == "#101020"


def test_untitled_gets_a_number_once_taken(tmp_path):
    assert unused_name(tmp_path, "untitled") == "untitled"
    (tmp_path / "untitled.theme.json").write_text("{}")
    (tmp_path / "untitled-2.theme.json").write_text("{}")
    assert unused_name(tmp_path, "untitled") == "untitled 3"


def test_create_refuses_canims_own_folder():
    with pytest.raises(ValueError, match="canim's own"):
        create_theme(a_theme(name="x"), theme.THEMES_DIR / "x.theme.json")


@pytest.mark.parametrize("name", theme.discover())
def test_every_shipped_theme_can_be_analyzed(name):
    result = analyze(theme.to_dict(theme.open(name)))
    assert set(result["contrast"]) >= {"identifier", "keyword", "background"}
