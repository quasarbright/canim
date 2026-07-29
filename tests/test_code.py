"""Tests that need manim loaded — construction and glyph addressing."""

from canim import Code
from canim.code import _runs


def test_runs_collapse_contiguous_indices():
    assert _runs((0, 1, 2)) == [(0, 2)]
    assert _runs((0, 2, 3, 7)) == [(0, 0), (2, 3), (7, 7)]


def test_glyph_index_is_the_character_offset():
    code = Code("(f x)")
    assert len(code.text) == len("(f x)")
    for token in code.tokens:
        assert code.source[token.start : token.end] == token.text


def test_group_of_one_token():
    code = Code("(lambda x)")
    lam = next(t for t in code.tokens if t.text == "lambda")
    assert len(code.group(lam)) == len("lambda")


def test_group_of_a_contiguous_run_includes_its_whitespace():
    # "(x x)" spans 5 characters including the space, so a run of its 4 tokens
    # must yield 5 glyphs — the space is what keeps the group's spacing intact.
    code = Code("(f (x x))")
    run = [t.index for t in code.tokens if 2 <= t.index <= 5]
    assert len(code.group(run)) == 5


def test_group_across_lines_is_still_one_slice():
    code = Code("(let\n  (x))")
    run = [t.index for t in code.tokens]
    assert len(code.group(run)) == len(code.source)


def test_group_of_disjoint_tokens():
    code = Code("(a b c)")
    a = next(t for t in code.tokens if t.text == "a")
    c = next(t for t in code.tokens if t.text == "c")
    assert len(code.group([a, c])) == 2


def test_indices_accepts_tokens_ints_and_iterables():
    code = Code("(a b)")
    assert code.indices(1) == (1,)
    assert code.indices(code.tokens[1]) == (1,)
    assert code.indices([2, 1, 1]) == (1, 2)


def test_tokens_are_colored_by_kind():
    code = Code("(let 42)")
    let = next(t for t in code.tokens if t.text == "let")
    num = next(t for t in code.tokens if t.text == "42")
    keyword = code.theme.color(let.kind)
    number = code.theme.color(num.kind)
    assert keyword != number
    assert code.group(let)[0].get_color().to_hex().lower() == keyword.lower()
    assert code.group(num)[0].get_color().to_hex().lower() == number.lower()


def test_whitespace_glyphs_stay_invisible_after_coloring():
    code = Code('(f "a b")')
    space = code.source.index(" ", 2)  # the space inside the string token
    assert code.text[space].fill_opacity == 0


def test_theme_covers_every_token_kind():
    from canim.lexer import Kind
    from canim.theme import ONE_DARK

    missing = [k for k in Kind if k not in ONE_DARK.colors]
    assert not missing, f"theme has no color for {missing}"


def test_distinct_kinds_get_distinct_colors():
    # Every kind reachable from set membership and token shape alone: builtin,
    # identifier, operator, string, literal, comment, delimiter.
    code = Code('(let ([x ,y]) (cons "s" 42 #t)) ; note')
    by_kind = {t.kind: code.group(t)[0].get_color().to_hex().lower() for t in code.tokens}
    assert len(by_kind) >= 7, f"only reached {sorted(k.value for k in by_kind)}"
    assert len(set(by_kind.values())) >= 6
