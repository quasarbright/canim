"""Tests that need manim loaded — construction and glyph addressing."""

import pytest

from canim import Code
from canim.code import _runs
from conftest import lisp


def test_runs_collapse_contiguous_indices():
    assert _runs((0, 1, 2)) == [(0, 2)]
    assert _runs((0, 2, 3, 7)) == [(0, 0), (2, 3), (7, 7)]


def test_glyph_index_is_the_character_offset():
    code = lisp("(f x)")
    assert len(code.text) == len("(f x)")
    for token in code.tokens:
        assert code.source[token.start : token.end] == token.text


def test_group_of_one_token():
    code = lisp("(lambda x)")
    lam = next(t for t in code.tokens if t.text == "lambda")
    assert len(code.group(lam)) == len("lambda")


def test_group_of_a_contiguous_run_includes_its_whitespace():
    # "(x x)" spans 5 characters including the space, so a run of its 4 tokens
    # must yield 5 glyphs — the space is what keeps the group's spacing intact.
    code = lisp("(f (x x))")
    run = [t.index for t in code.tokens if 2 <= t.index <= 5]
    assert len(code.group(run)) == 5


def test_group_across_lines_is_still_one_slice():
    code = lisp("(let\n  (x))")
    run = [t.index for t in code.tokens]
    assert len(code.group(run)) == len(code.source)


def test_group_of_disjoint_tokens():
    code = lisp("(a b c)")
    a = next(t for t in code.tokens if t.text == "a")
    c = next(t for t in code.tokens if t.text == "c")
    assert len(code.group([a, c])) == 2


def test_indices_accepts_tokens_ints_and_iterables():
    code = lisp("(a b)")
    assert code.indices(1) == (1,)
    assert code.indices(code.tokens[1]) == (1,)
    assert code.indices([2, 1, 1]) == (1, 2)


def test_tokens_are_colored_by_kind():
    code = lisp("(let 42)")
    let = next(t for t in code.tokens if t.text == "let")
    num = next(t for t in code.tokens if t.text == "42")
    keyword = code.theme.color(let.kind)
    number = code.theme.color(num.kind)
    assert keyword != number
    assert code.group(let)[0].get_color().to_hex().lower() == keyword.lower()
    assert code.group(num)[0].get_color().to_hex().lower() == number.lower()


def test_whitespace_glyphs_stay_invisible_after_coloring():
    code = lisp('(f "a b")')
    space = code.source.index(" ", 2)  # the space inside the string token
    assert code.text[space].fill_opacity == 0


def test_theme_covers_every_token_kind():
    from canim.lexer import Kind
    from canim import theme

    for name in theme.discover():
        missing = [k for k in Kind if k not in theme.open(name).colors]
        assert not missing, f"{name} has no color for {missing}"


def test_distinct_kinds_get_distinct_colors():
    # Every kind reachable from set membership and token shape alone: builtin,
    # identifier, operator, string, literal, comment, delimiter.
    code = lisp('(let ([x ,y]) (cons "s" 42 #t)) ; note')
    by_kind = {t.kind: code.group(t)[0].get_color().to_hex().lower() for t in code.tokens}
    assert len(by_kind) >= 7, f"only reached {sorted(k.value for k in by_kind)}"
    assert len(set(by_kind.values())) >= 6


# --- select ----------------------------------------------------------------


def test_select_is_a_vgroup_of_the_glyphs():
    code = lisp("(let ([tmp a]) tmp)")
    sel = code.select(code.all("tmp"))
    assert len(sel) == 6  # two three-character tokens
    assert [t.text for t in sel.tokens] == ["tmp", "tmp"]


def test_select_animates_like_any_vgroup():
    # The point of Selection being a VGroup: no bespoke tween proxies needed.
    code = lisp("(f tmp)")
    sel = code.select("tmp")
    assert hasattr(sel, "animate")
    assert len(sel) == 3


def test_disjoint_tokens_get_one_run_each():
    # A single box round the whole selection would span everything between
    # them, which is exactly the mistake the review render caught.
    code = lisp("(let ([tmp a]) tmp)")
    sel = code.select(code.all("tmp"))
    assert len(sel.runs) == 2
    assert len(sel.boxes()) == 2


def test_a_contiguous_run_is_one_box():
    code = lisp("(g (h x))")
    sel = code.select(code.nth("(h x)"))
    assert len(sel.runs) == 1
    assert len(sel.boxes()) == 1
    # ...and it carries the whitespace between its tokens
    assert len(sel) == len("(h x)")


def test_select_accepts_bare_strings_and_refs():
    code = lisp("(f a b)")
    assert code.select("a").indices == (2,)
    assert code.select(code.nth("b")).indices == (3,)
    assert code.select([2, 3]).indices == (2, 3)


# --- clone -----------------------------------------------------------------


def test_clone_matches_source_styling_and_position():
    code = lisp("(f x)", font_size=31, line_spacing=1.4)
    twin = code.clone()
    assert twin.source == code.source
    assert twin.language is code.language
    assert twin is not code
    assert twin.text is not code.text
    assert abs(twin.width - code.width) < 1e-9
    assert abs(twin.height - code.height) < 1e-9
    assert (twin.get_center() == code.get_center()).all()


def test_clone_is_independent():
    code = lisp("(f x)")
    twin = code.clone()
    twin.shift([1, 0, 0])
    assert not (twin.get_center() == code.get_center()).all()


def test_clone_keeps_its_own_tokens():
    code = lisp("(f x)")
    twin = code.clone()
    assert [t.text for t in twin.tokens] == [t.text for t in code.tokens]
    assert twin.tokens is not code.tokens


def test_clone_preserves_transforms_applied_after_construction():
    # A clone rebuilt from the constructor arguments came back at full size and
    # sat on top of the scaled original, doubled.
    code = lisp("(f x)").scale(0.78).shift([1.5, -0.5, 0])
    twin = code.clone()
    assert abs(twin.width - code.width) < 1e-9
    assert (twin.get_center() == code.get_center()).all()


def test_clone_addresses_its_own_glyphs():
    code = lisp("(f x)").scale(0.5)
    twin = code.clone()
    assert twin.group(twin.nth("f"))[0] is not code.group(code.nth("f"))[0]
    assert twin.text is twin.submobjects[0]


def test_the_language_is_required():
    # It used to default to Lisp. A block silently lexed as the wrong
    # language still renders — it just colors and matches by another
    # language's rules, which is a bug with nothing to notice.
    with pytest.raises(TypeError, match="language"):
        Code("def f(): pass")
