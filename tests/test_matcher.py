import pytest

from canim.languages import LISP, PYTHON
from canim.lexer import lex
from canim.matcher import MappingError, Op, dump, match


def pairs(a, b, entries=(), language=LISP):
    """(source index, source text) -> destination index, or None if it fades."""
    src, dst = lex(a, language), lex(b, language)
    out = {}
    for c in match(src, dst, entries):
        if c.op is Op.FADE_IN:
            continue
        for i in c.src_tokens:
            out[i] = None if c.op is Op.FADE_OUT else c.dst_tokens
    return src, dst, out


def moved(a, b, entries=(), language=LISP):
    """Readable summary: [(src_text, src_idx, dst_idx or None)]."""
    src, dst, out = pairs(a, b, entries, language)
    return [
        (src[i].text, i, None if v is None else (v[0] if len(v) == 1 else v))
        for i, v in sorted(out.items())
    ]


def faded_in(a, b, entries=(), language=LISP):
    src, dst = lex(a, language), lex(b, language)
    return [
        dst[j].text
        for c in match(src, dst, entries)
        if c.op is Op.FADE_IN
        for j in c.dst_tokens
    ]


# --- the cases the whole design exists for ---------------------------------


def test_reorder_moves_everything():
    #  (a + b) -> (+ a b)
    assert moved("(a + b)", "(+ a b)") == [
        ("(", 0, 0),
        ("a", 1, 2),
        ("+", 2, 1),
        ("b", 3, 3),
        (")", 4, 4),
    ]


def test_dropping_a_nesting_level_keeps_bracket_pairs_together():
    # The bug the forced-partner rule exists for: without it the surviving
    # `)` is the inner one, so the outer pair comes apart.
    #  0:(  1:f  2:(  3:x  4:y  5:)  6:)
    assert moved("(f (x y))", "(f x y)") == [
        ("(", 0, 0),
        ("f", 1, 1),
        ("(", 2, None),
        ("x", 3, 2),
        ("y", 4, 3),
        (")", 5, None),
        (")", 6, 4),  # the OUTER closer survives, dragged by its opener
    ]


def test_barf_keeps_pairs_paired():
    #  (())  ->  ()()
    #  A B C D      W X Y Z      A-D and B-C pair; W-X and Y-Z pair
    got = dict((i, d) for _, i, d in [(t, i, d) for t, i, d in moved("(())", "()()")])
    assert got == {0: 0, 3: 1, 1: 2, 2: 3}
    # i.e. A->W, D->X, B->Y, C->Z — every survivor is half of a real pair
    assert got[0] == 0 and got[3] == 1  # source outer pair -> dest first pair
    assert got[1] == 2 and got[2] == 3  # source inner pair -> dest second pair


def test_naive_matching_would_have_broken_the_barf_case():
    # Guard against someone deleting _force_partner: naive greedy gives
    # A->W B->Y C->X D->Z, which splits both pairs.
    got = dict((i, d) for _, i, d in moved("(())", "()()"))
    assert got != {0: 0, 1: 2, 2: 1, 3: 3}


# --- fades -----------------------------------------------------------------


def test_creation_and_deletion_need_no_help():
    assert moved("a", "(f a)") == [("a", 0, 2)]
    assert faded_in("a", "(f a)") == ["(", "f", ")"]

    assert moved("(f a)", "a") == [("(", 0, None), ("f", 1, None), ("a", 2, 0), (")", 3, None)]


def test_extra_duplicates_fade_prefix_first():
    assert moved("a", "(a a)") == [("a", 0, 1)]
    assert moved("(a a)", "a") == [("(", 0, None), ("a", 1, 0), ("a", 2, None), (")", 3, None)]


def test_unbalanced_source_does_not_raise():
    assert moved("(f (g", "(f g)")  # just needs to not blow up


# --- python ----------------------------------------------------------------


def test_python_flatten():
    # The exact case that came apart under the old Motion Canvas matcher: the
    # surviving `]` was the inner one, so the outer pair split.
    #  0:[ 1:f 2:, 3:[ 4:x 5:, 6:y 7:] 8:]
    by_index = {i: d for _, i, d in moved("[f, [x, y]]", "[f, x, y]", language=PYTHON)}
    assert by_index[0] == 0  # outer [ ...
    assert by_index[8] == 6  # ... paired with the outer ]
    assert by_index[3] is None and by_index[7] is None  # the inner pair fades
    assert by_index[4] == 3 and by_index[6] == 5  # x and y slide left


# --- the mapping -----------------------------------------------------------


def entry(frm, to):
    """Build one already-resolved entry from flat index lists."""
    return (tuple((i,) for i in frm), tuple((j,) for j in to))


def test_morph_is_never_inferred_but_can_be_stated():
    assert moved("(let x)", "(lambda x)") == [
        ("(", 0, 0),
        ("let", 1, None),  # different text -> unrelated
        ("x", 2, 2),
        (")", 3, 3),
    ]
    src, dst = lex("(let x)", LISP), lex("(lambda x)", LISP)
    ops = {c.op for c in match(src, dst, [entry([1], [1])])}
    assert Op.MORPH in ops


def test_clone():
    src, dst = lex("(swap a b)", LISP), lex("(let (t a) (set a b))", LISP)
    a_dst = [t.index for t in dst if t.text == "a"]
    clones = [c for c in match(src, dst, [entry([2], a_dst)]) if c.op is Op.CLONE]
    assert len(clones) == 1
    assert clones[0].dst_tokens == tuple(a_dst)


def test_merge():
    src, dst = lex("(f tmp tmp)", LISP), lex("(f tmp)", LISP)
    merges = [c for c in match(src, dst, [entry([2, 3], [2])]) if c.op is Op.MERGE]
    assert len(merges) == 1
    assert merges[0].src_tokens == (2, 3)


def test_group_clone_pairs_positionally():
    src = lex("(g (h x))", LISP)
    dst = lex("((h x) (h x))", LISP)
    group = tuple(range(2, 7))  # ( h x ) in the source, as one run
    dest_runs = ((1, 2, 3, 4), (5, 6, 7, 8))
    out = match(src, dst, [((group,), dest_runs)])
    clone = next(c for c in out if c.op is Op.CLONE)
    assert clone.src == (group,)
    assert clone.dst == dest_runs


def test_manual_entries_do_not_force_partners():
    # Naming only the opener must leave the closer to ordinary greedy matching,
    # which is what makes the beta-reduction paren redirect precise.
    src, dst = lex("((a))", LISP), lex("(a)", LISP)
    out = match(src, dst, [entry([1], [0])])
    forced = [c for c in out if c.src_tokens == (4,) and c.dst_tokens == (2,)]
    assert not forced or forced[0].manual is False


# --- errors ----------------------------------------------------------------


def test_unresolvable_counts_raise():
    src, dst = lex("(a a a)", LISP), lex("(a a)", LISP)
    with pytest.raises(MappingError, match="split this into separate entries"):
        match(src, dst, [entry([1, 2, 3], [1, 2])])


def test_double_claim_names_the_token():
    src, dst = lex("(a b)", LISP), lex("(a b)", LISP)
    with pytest.raises(MappingError, match=r"'a'.*claimed by more than one entry"):
        match(src, dst, [entry([1], [1]), entry([1], [2])])


# --- the dump --------------------------------------------------------------


def test_dump_is_readable_and_marks_manual_entries():
    src, dst = lex("(let x)", LISP), lex("(lambda x)", LISP)
    text = dump(src, dst, match(src, dst, [entry([1], [1])]))
    assert "source" in text and "destination" in text
    assert "morph" in text
    assert "*" in text  # the manual entry is flagged
    assert "·" in text or "fade" in text


# --- separators ------------------------------------------------------------


def columns(a, b, language=LISP):
    """{token index: (text, source col, dest col)} for every matched token."""
    src, dst = lex(a, language), lex(b, language)
    out = {}
    for c in match(src, dst):
        if c.op is not Op.MOVE:
            continue
        i, j = c.src_tokens[0], c.dst_tokens[0]
        out[i] = (src[i].text, src[i].col, dst[j].col)
    return out


def test_separators_pair_by_ordinal_not_by_neighbour():
    """The k-th comma becomes the k-th comma.

    `[result, =, ...]` -> `[=, result, ...]` swaps two elements of different
    widths, so the separator between them keeps its structural slot while its
    column changes. Only the first comma moves; it slides left because the
    element in front of it shrank from `result` to `=`.

    The alternative reading — a comma travels with the element it follows —
    would keep them from crossing, but it needs structure the lexer doesn't
    have. Do it with a mapping entry if a scene wants it.
    """
    cols = columns("[result, =, [w, *, h]]", "[=, result, [*, w, h]]", PYTHON)
    commas = {i: v for i, v in cols.items() if v[0] == ","}

    assert [i for i in sorted(commas)] == [2, 4, 7, 9]
    moved = {i: v[2] - v[1] for i, v in commas.items() if v[1] != v[2]}
    assert moved == {2: -5}, "only the first separator should shift"

    # ...and it crosses `result`, which is going the other way.
    assert cols[1][0] == "result" and cols[1][2] - cols[1][1] == +3


def test_operands_swap_around_their_operator():
    cols = columns("[result, =, [w, *, h]]", "[=, result, [*, w, h]]", PYTHON)
    assert cols[3][0] == "=" and cols[3][2] < cols[3][1]  # = moves left
    assert cols[1][0] == "result" and cols[1][2] > cols[1][1]  # result moves right
    assert cols[8][0] == "*" and cols[8][2] < cols[8][1]  # and one level down
    assert cols[6][0] == "w" and cols[6][2] > cols[6][1]
