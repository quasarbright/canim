"""Language definitions for the lexer.

A language decides what a word looks like, which characters pair, and which
words are keywords, builtins or literals. Every one of those is a set lookup or
a regex on the token's own text — nothing here needs context. Colors live in
``theme``; these are grammar, not palette.
"""

from __future__ import annotations

import re

from .lexer import Language

# A lisp symbol is a run of characters that aren't whitespace, a delimiter, or
# reader syntax — roughly how a real reader works, and why `set!`, `+` and
# `list->vector` each come out as one token.
LISP = Language(
    name="lisp",
    word=re.compile(r"[^\s()\[\]{}'\"`,;]+"),
    number=re.compile(r"[+-]?\d+(\.\d+)?"),
    # Reserved to control flow and binding syntax. The define-family reads as a
    # named form rather than a reserved word, so it sits with the builtins.
    keywords=frozenset(
        {
            "if", "cond", "case", "else", "when", "unless", "begin",
            "and", "or", "not", "match", "syntax-rules",
            "quote",
        }
    ),
    builtins=frozenset(
        {
            # Named forms you call, like `list` or `let` — not reserved syntax.
            # Their reader shorthands ` and , are still operators.
            "quasiquote", "unquote", "unquote-splicing", "lambda",
            "define", "define-syntax", "define-values", "defmacro", "defvar",
            "let", "let*", "letrec", "let-values", "set!", "setf",
            "require", "provide", "module+", "all-defined-out", "gensym",
            "car", "cdr", "caar", "cadr", "cddr", "cons", "list", "append",
            "map", "filter", "foldl", "foldr", "apply", "length", "reverse",
            "vector", "vector-ref", "vector-set!", "hash", "hash-ref",
            "display", "displayln", "printf", "newline", "error", "void",
            "null?", "pair?", "list?", "eq?", "eqv?", "equal?", "zero?",
            "number?", "symbol?", "string?", "procedure?",
            "string-append", "symbol->string", "string->symbol", "list->vector",
            "+", "-", "*", "/", "=", "<", ">", "<=", ">=", "modulo", "remainder",
        }
    ),
    literals=frozenset({"#t", "#f", "#true", "#false", "null", "nil", "empty"}),
    delimiters={"(": ")", "[": "]", "{": "}"},
    # ,@ before , so the splice doesn't lex as two tokens.
    operators=(",@", "`", ",", "'"),
    line_comment=";",
)

PYTHON = Language(
    name="python",
    word=re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+\.?\d*"),
    number=re.compile(r"\d+\.?\d*"),
    keywords=frozenset(
        {
            "def", "class", "return", "yield", "lambda",
            "if", "elif", "else", "for", "while", "break", "continue", "pass",
            "in", "is", "not", "and", "or",
            "import", "from", "as", "with", "try", "except", "finally",
            "raise", "assert", "global", "nonlocal", "del", "match", "case",
        }
    ),
    builtins=frozenset(
        {
            "print", "len", "range", "isinstance", "sorted", "enumerate", "zip",
            "str", "int", "float", "bool", "bytes", "list", "dict", "set",
            "tuple", "type", "super", "min", "max", "sum", "abs", "any", "all",
            "open", "next", "iter", "repr", "round", "map", "filter",
            "getattr", "setattr", "hasattr", "callable",
        }
    ),
    literals=frozenset({"None", "True", "False", "Ellipsis"}),
    delimiters={"(": ")", "[": "]", "{": "}"},
    # Longest first: -> before -, ** before *, >> before >.
    operators=(
        "->", "==", "!=", "<=", ">=", "//", "**", ":=", "<<", ">>",
        "=", "+", "-", "*", "/", "<", ">", "%", "|", "&", "^", "~", "@",
    ),
    punctuation=",:.;",
    line_comment="#",
    string_delims="\"'",
    string_prefixes="fFrRbBuU",
)

JAVASCRIPT = Language(
    name="javascript",
    word=re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*|\d+\.?\d*"),
    number=re.compile(r"\d+\.?\d*"),
    keywords=frozenset(
        {
            "const", "let", "var", "function", "return", "yield",
            "if", "else", "for", "while", "do", "break", "continue", "switch",
            "case", "default", "class", "extends", "new", "delete", "typeof",
            "instanceof", "in", "of", "this", "super",
            "import", "export", "from", "as", "async", "await",
            "try", "catch", "finally", "throw",
        }
    ),
    builtins=frozenset(
        {
            "console", "log", "Math", "JSON", "Object", "Array", "String",
            "Number", "Boolean", "Promise", "Set", "Map", "Symbol", "Error",
            "parseInt", "parseFloat", "isNaN", "length",
            "push", "pop", "shift", "map", "filter", "reduce", "forEach",
            "join", "split", "slice", "concat", "includes", "keys", "values",
        }
    ),
    literals=frozenset({"true", "false", "null", "undefined", "NaN", "Infinity"}),
    delimiters={"(": ")", "[": "]", "{": "}"},
    # Longest first, as everywhere: === before ==, ?. before ?, ... before .
    operators=(
        "===", "!==", "...", "**=", "&&=", "||=", "??=", ">>>",
        "==", "!=", "<=", ">=", "=>", "&&", "||", "??", "?.",
        "++", "--", "+=", "-=", "*=", "/=", "**", "<<", ">>",
        "=", "+", "-", "*", "/", "<", ">", "%", "!", "&", "|", "^", "~", "?",
    ),
    punctuation=",:;.",
    line_comment="//",
    # The backtick makes a template literal one string token, the same way a
    # quote does — so `${a}` arrives as part of the literal and gets painted by
    # hand, exactly like python's f-string braces.
    string_delims="\"'`",
)

BY_NAME = {"lisp": LISP, "python": PYTHON, "javascript": JAVASCRIPT, "js": JAVASCRIPT}


def resolve(language: Language | str) -> Language:
    if isinstance(language, Language):
        return language
    try:
        return BY_NAME[language]
    except KeyError:
        raise ValueError(
            f"unknown language {language!r}; known: {sorted(BY_NAME)}"
        ) from None
