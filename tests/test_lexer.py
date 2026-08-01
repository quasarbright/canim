import pytest

from canim.languages import LISP, PYTHON, resolve
from canim.lexer import Kind, lex


def texts(source, language=LISP):
    return [t.text for t in lex(source, language)]


def kinds(source, language=LISP):
    return [(t.text, t.kind) for t in lex(source, language)]


# --- lisp words ------------------------------------------------------------


def test_punctuation_heavy_identifiers_are_single_tokens():
    assert texts("(set! a b)") == ["(", "set!", "a", "b", ")"]
    assert texts("(+ 1 2)") == ["(", "+", "1", "2", ")"]
    assert texts("(list->vector xs)") == ["(", "list->vector", "xs", ")"]


def test_keywords_versus_identifiers():
    assert kinds("(lambda x)") == [
        ("(", Kind.DELIMITER),
        ("lambda", Kind.KEYWORD),
        ("x", Kind.IDENTIFIER),
        (")", Kind.DELIMITER),
    ]


def test_numbers():
    by_text = {t.text: t.kind for t in lex("(f 42 -1.5 x1)", LISP)}
    assert by_text["42"] is Kind.LITERAL
    assert by_text["-1.5"] is Kind.LITERAL
    assert by_text["x1"] is Kind.IDENTIFIER


# --- reader macros ---------------------------------------------------------


def test_splice_beats_comma():
    assert texts("`(f ,@xs ,y)") == ["`", "(", "f", ",@", "xs", ",", "y", ")"]


def test_reader_macros_are_operators():
    assert [t.kind for t in lex(",x", LISP)] == [Kind.OPERATOR, Kind.IDENTIFIER]


def test_quote_does_not_glue_to_the_symbol():
    assert texts("'(a b)") == ["'", "(", "a", "b", ")"]


# --- strings and comments --------------------------------------------------


def test_string_is_one_token_and_hides_its_contents():
    toks = lex('(f "a b (c)" d)', LISP)
    assert [t.text for t in toks] == ["(", "f", '"a b (c)"', "d", ")"]
    assert toks[2].kind is Kind.STRING


def test_a_prefix_belongs_to_the_string_it_introduces():
    # `f` on its own would lex as an identifier and stay colored as code, which
    # leaves the quote looking like it starts one character late.
    toks = lex('x = f"a {b} c"', PYTHON)
    assert [t.text for t in toks] == ["x", "=", 'f"a {b} c"']
    assert toks[2].kind is Kind.STRING
    assert texts('rb"a"', PYTHON) == ['rb"a"']


def test_a_prefix_letter_is_only_a_prefix_next_to_a_quote():
    assert texts("format(x)", PYTHON) == ["format", "(", "x", ")"]
    assert texts("f(x)", PYTHON) == ["f", "(", "x", ")"]


def test_escaped_quote_does_not_end_the_string():
    assert texts(r'"a\"b"') == [r'"a\"b"']


def test_comment_runs_to_end_of_line():
    toks = lex("(f) ; (not code)\n(g)", LISP)
    assert [t.text for t in toks] == ["(", "f", ")", "; (not code)", "(", "g", ")"]
    assert toks[3].kind is Kind.COMMENT


# --- partners --------------------------------------------------------------


def partners(source, language=LISP):
    toks = lex(source, language)
    return {t.index: t.partner for t in toks if t.kind is Kind.DELIMITER}


def test_nested_partners():
    #  0 1 2 3 4
    #  ( ( ) ( ) )   -- indices below are token indices
    assert partners("(()())") == {0: 5, 1: 2, 2: 1, 3: 4, 4: 3, 5: 0}


def test_partners_across_lines():
    toks = lex("(let ([x e])\n  b)", LISP)
    opener = toks[0]
    assert opener.text == "(" and toks[opener.partner].text == ")"
    assert toks[opener.partner].line == 1


def test_unbalanced_opener_has_no_partner():
    toks = lex("(f (g", LISP)
    assert all(t.partner is None for t in toks if t.kind is Kind.DELIMITER)


def test_unbalanced_closer_has_no_partner():
    toks = lex("f)", LISP)
    assert toks[1].partner is None


def test_mismatched_closer_does_not_consume_the_opener():
    # `]` must not pop the `(`, or every pair after it shifts.
    #   0:(  1:a  2:]  3:(  4:b  5:)  6:)
    toks = lex("(a] (b))", LISP)
    by_index = {t.index: t.partner for t in toks if t.kind is Kind.DELIMITER}
    assert by_index[2] is None  # the stray ]
    assert by_index[3] == 5 and by_index[5] == 3  # (b) still pairs
    assert by_index[0] == 6 and by_index[6] == 0  # and so does the outer form


def test_square_and_round_pair_independently():
    toks = lex("([x])", LISP)
    assert toks[0].partner == 4
    assert toks[1].partner == 3


# --- positions -------------------------------------------------------------


def test_offsets_line_and_column():
    source = "(let ([x e])\n  (set! a b))"
    toks = lex(source, LISP)
    for t in toks:
        assert source[t.start : t.end] == t.text
    second_line = [t for t in toks if t.line == 1]
    assert second_line[0].text == "(" and second_line[0].col == 2


def test_every_non_whitespace_character_is_covered():
    source = "(defmacro swap! (a b)\n  `(let ([tmp ,a])\n     (set! ,a ,b)))"
    toks = lex(source, LISP)
    covered = sum(len(t.text) for t in toks)
    assert covered == sum(1 for c in source if not c.isspace())


# --- python ----------------------------------------------------------------


def test_python_def():
    assert texts("def area(w, h):", PYTHON) == [
        "def", "area", "(", "w", ",", "h", ")", ":",
    ]


def test_python_comment_and_string():
    toks = lex("x = 'a' # note\n", PYTHON)
    assert [t.kind for t in toks][-2:] == [Kind.STRING, Kind.COMMENT]


# --- resolve ---------------------------------------------------------------


def test_resolve_by_name_and_passthrough():
    assert resolve("lisp") is LISP
    assert resolve(LISP) is LISP
    with pytest.raises(ValueError, match="unknown language"):
        resolve("brainfuck")


# --- classification is stateless -------------------------------------------


def kind_of(source, text, language=LISP):
    return next(t.kind for t in lex(source, language) if t.text == text)


def test_keyword_and_builtin_come_from_set_membership():
    assert kind_of("(lambda x)", "lambda") is Kind.KEYWORD
    assert kind_of("(require x)", "require") is Kind.BUILTIN
    assert kind_of("(+ 1 2)", "+") is Kind.BUILTIN
    # The define-family reads as a named form, not a reserved word.
    assert kind_of("(defmacro f ())", "defmacro") is Kind.BUILTIN
    assert kind_of("(define x 1)", "define") is Kind.BUILTIN
    assert kind_of("(let ([x 1]) x)", "let") is Kind.BUILTIN


def test_every_other_identifier_is_plain():
    # Shape and position must not matter: a defined name, a capitalised name
    # and an ALL_CAPS name are all just identifiers.
    assert kind_of("(defmacro swap! (a b))", "swap!") is Kind.IDENTIFIER
    assert kind_of("(f Language)", "Language") is Kind.IDENTIFIER
    assert kind_of("(f BY_NAME)", "BY_NAME") is Kind.IDENTIFIER
    assert kind_of("def resolve(x): pass", "resolve", PYTHON) is Kind.IDENTIFIER


def test_a_tokens_kind_does_not_depend_on_its_neighbours():
    """The property that keeps coloring stable mid-transformation.

    Half the frames in the video are valid in no language; a kind that depended
    on context would flicker as tokens move.
    """
    contexts = [
        "(define x 1)",
        "(f x)",
        "x",
        "(let ([x 1]) x)",
        ") x (",  # not valid anything
    ]
    kinds = {kind_of(c, "x") for c in contexts}
    assert kinds == {Kind.IDENTIFIER}

    for source in ("(define lambda 1)", "(lambda)", ") lambda ("):
        assert kind_of(source, "lambda") is Kind.KEYWORD


def test_python_builtins_are_still_set_lookups():
    assert kind_of("isinstance(x, Language)", "isinstance", PYTHON) is Kind.BUILTIN
    assert kind_of("isinstance(x, Language)", "Language", PYTHON) is Kind.IDENTIFIER


# --- operators and literals ------------------------------------------------


def test_lisp_reader_macros_are_operators():
    assert [t.kind for t in lex("`(f ,@xs ,y 'z)", LISP) if t.kind is Kind.OPERATOR]
    assert kind_of("`(a)", "`") is Kind.OPERATOR
    assert kind_of("(f ,a)", ",") is Kind.OPERATOR
    assert kind_of("(f ,@a)", ",@") is Kind.OPERATOR
    assert kind_of("'(a)", "'") is Kind.OPERATOR


def test_python_operators_beat_punctuation():
    by_text = {t.text: t.kind for t in lex("a = b -> c, d: e", PYTHON)}
    assert by_text["="] is Kind.OPERATOR
    assert by_text["->"] is Kind.OPERATOR
    assert by_text[","] is Kind.PUNCTUATION
    assert by_text[":"] is Kind.PUNCTUATION


def test_longest_operator_wins():
    assert texts("a -> b", PYTHON) == ["a", "->", "b"]
    assert texts("a == b", PYTHON) == ["a", "==", "b"]
    assert texts("a >= b", PYTHON) == ["a", ">=", "b"]


def test_literals_cover_numbers_and_value_words():
    assert kind_of("(f 42)", "42") is Kind.LITERAL
    assert kind_of("(f 3.14)", "3.14") is Kind.LITERAL
    assert kind_of("(f #t)", "#t") is Kind.LITERAL
    assert kind_of("f(None)", "None", PYTHON) is Kind.LITERAL
    assert kind_of("f(True)", "True", PYTHON) is Kind.LITERAL
