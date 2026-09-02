import pytest

from canim.matcher import MappingError, Op, match
from canim.refs import RefError, resolve_mapping
from conftest import lisp


def indices(code, mapping):
    return resolve_mapping(mapping, code, code)


# --- the vocabulary --------------------------------------------------------


def test_bare_string_is_the_first_occurrence():
    code = lisp("(f a a)")
    assert code.nth("a").indices == (2,)


def test_nth_picks_a_later_occurrence():
    code = lisp("(f a a)")
    assert code.nth("a", 1).indices == (3,)


def test_all_returns_every_occurrence():
    code = lisp("(f a a)")
    assert [r.indices for r in code.all("a")] == [(2,), (3,)]


def test_matching_is_token_level_not_substring():
    # `swap` contains the letters of `a`... but not the token.
    code = lisp("(swap a b)")
    assert code.nth("a").indices == (2,)
    assert code.tokens[2].text == "a"


def test_a_ref_cannot_land_inside_a_string_or_comment():
    code = lisp('(f "a b" a) ; a')
    # only the real token, not the `a` inside the string or the comment
    assert [r.indices for r in code.all("a")] == [(3,)]


# --- sequences -------------------------------------------------------------


def test_sequence_ref_spans_a_run():
    code = lisp("(g (h x))")
    assert code.nth("(h x)").indices == (2, 3, 4, 5)


def test_sequence_ref_ignores_whitespace_and_line_breaks():
    flat = lisp("(let (x) (f x))")
    broken = lisp("(let (x)\n     (f  x))")
    assert flat.nth("(f x)").indices == broken.nth("(f x)").indices


def test_sequence_ref_finds_each_occurrence():
    code = lisp("((lambda (x) (x x)) (lambda (x) (x x)))")
    runs = [r.indices for r in code.all("(lambda (x) (x x))")]
    assert len(runs) == 2
    assert runs[0][0] == 1 and runs[1][0] == 11


def test_a_run_that_is_not_contiguous_is_not_a_match():
    code = lisp("(f x y)")
    with pytest.raises(RefError, match="does not appear"):
        code.nth("(x)")


# --- partner ---------------------------------------------------------------


def test_partner_of_a_delimiter():
    code = lisp("(f (x))")
    assert code.nth("(").partner.indices == (5,)
    assert code.nth("(", 1).partner.indices == (4,)


def test_partner_of_a_run_is_an_error():
    code = lisp("(f (x))")
    with pytest.raises(RefError, match="only meaningful for a single delimiter"):
        code.nth("(x)").partner


def test_partner_of_a_non_delimiter_is_an_error():
    code = lisp("(f x)")
    with pytest.raises(RefError, match="not a delimiter"):
        code.nth("f").partner


def test_partner_of_an_unbalanced_delimiter_is_an_error():
    code = lisp("(f (x)")
    with pytest.raises(RefError, match="unbalanced"):
        code.nth("(").partner


# --- entries ---------------------------------------------------------------


def test_counts_are_in_refs_not_tokens():
    src = lisp("(g (h x))")
    dst = lisp("((h x) (h x))")
    # one ten-token group cloning into two, not 5 tokens into 10
    entries = resolve_mapping([([src.nth("(h x)")], dst.all("(h x)"))], src, dst)
    frm, to = entries[0]
    assert len(frm) == 1 and len(to) == 2
    assert len(frm[0]) == 4  # ...and the group still carries its four tokens


def test_a_list_of_refs_and_a_bare_ref_mix():
    src = lisp("(f a b)")
    dst = lisp("(f a b)")
    entries = resolve_mapping([(["a", src.nth("b")], ["a", dst.nth("b")])], src, dst)
    assert entries[0][0] == ((2,), (3,))


# --- the seven errors ------------------------------------------------------


def test_typo_in_a_ref():
    code = lisp("(f tmp)")
    with pytest.raises(RefError, match="does not appear"):
        code.nth("tmpp")


def test_nth_out_of_range_says_how_many_there_are():
    code = lisp("(f tmp)")
    with pytest.raises(RefError, match="appears 1 time"):
        code.nth("tmp", 3)


def test_ref_from_the_wrong_block():
    src, dst = lisp("(f a)"), lisp("(g a)")
    with pytest.raises(RefError, match="different Code block"):
        resolve_mapping([([dst.nth("a")], [dst.nth("a")])], src, dst)


def test_unresolvable_counts():
    src, dst = lisp("(f a a a)"), lisp("(f a a)")
    entries = resolve_mapping([(src.all("a"), dst.all("a"))], src, dst)
    with pytest.raises(MappingError, match="split this into separate entries"):
        match(src.tokens, dst.tokens, entries)


def test_the_same_token_in_two_entries():
    src, dst = lisp("(f a b)"), lisp("(f a b)")
    entries = resolve_mapping(
        [(["a"], ["a"]), (["a"], ["b"])], src, dst
    )
    with pytest.raises(MappingError, match="claimed by more than one entry"):
        match(src.tokens, dst.tokens, entries)


# --- the exclusion idiom ---------------------------------------------------


def test_fading_a_pair_by_hand_frees_the_destination_parens():
    """`(let ([x e]) b)` -> `((lambda (x) b) e)`.

    Left alone, greedy hands the binding-group parens to the lambda's parens,
    which is not where they come from. Fading them by hand takes them out of
    the pool so the destination's inner parens fade in instead.
    """
    src = lisp("(let ([x e]) b)")
    dst = lisp("((lambda (x) b) e)")

    bindings = src.nth("(", 1)
    mapping = [
        (["let"], ["lambda"]),
        ([bindings, bindings.partner], []),
    ]
    entries = resolve_mapping(mapping, src, dst)
    corr = match(src.tokens, dst.tokens, entries)

    faded = {i for c in corr if c.op is Op.FADE_OUT for i in c.src_tokens}
    assert bindings.indices[0] in faded
    assert bindings.partner.indices[0] in faded

    # x, e and b travel; the outer parens keep their pair
    moved = {c.src_tokens[0]: c.dst_tokens[0] for c in corr if c.op is Op.MOVE}
    outer = src.nth("(")
    assert moved[outer.indices[0]] == 0
    assert moved[outer.partner.indices[0]] == dst.nth(")", 2).indices[0]


def test_manual_entries_still_do_not_force_partners():
    src, dst = lisp("((a))"), lisp("(a)")
    entries = resolve_mapping([([src.nth("(", 1)], [dst.nth("(")])], src, dst)
    corr = match(src.tokens, dst.tokens, entries)
    manual = [c for c in corr if c.manual]
    assert len(manual) == 1  # only the opener; the closer was left alone
