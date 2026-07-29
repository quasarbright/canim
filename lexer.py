"""Lexing source into positioned tokens, and resolving delimiter partners.

Deliberately imports no manim: this half of the pipeline is pure data, which is
what makes it testable without a browser or a render.

Two invariants the rest of the library leans on:

* Every character of the source belongs to exactly one token or is whitespace.
  ``lex`` asserts this, because a gap here silently misaligns every glyph slice
  downstream.
* A delimiter's ``partner`` is the token that balances it, or ``None``. Nothing
  requires the source to be balanced — unmatched delimiters simply have no
  partner and behave as ordinary tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Kind(Enum):
    """A token's kind is a pure function of its own text.

    No lookbehind, no parser state, nothing that depends on a neighbouring
    token — so coloring can never drift out of sync with the code as it is
    transformed mid-animation, when the text on screen is often valid in no
    language at all. It costs some richness: telling a name being *defined*
    from a name being *used* needs context we deliberately don't have.
    """

    IDENTIFIER = "identifier"
    KEYWORD = "keyword"
    """Special forms and control flow: define, lambda, if, def, return."""
    BUILTIN = "builtin"
    """Named forms and standard callables: defmacro, let, cons, print."""
    OPERATOR = "operator"
    """Lisp reader macros — ` , ,@ ' — and infix operators like = + -> ."""
    LITERAL = "literal"
    """Numbers, and words that are values in themselves: #t, None, True."""
    DELIMITER = "delimiter"
    """Paired: ( ) [ ] { }. The only kind that carries a partner."""
    PUNCTUATION = "punctuation"
    """Unpaired separators that aren't operators: commas and colons."""
    STRING = "string"
    COMMENT = "comment"


@dataclass
class Token:
    text: str
    kind: Kind
    line: int
    col: int
    start: int
    """Character offset into the source. Also the glyph index — manim's Text
    emits one submobject per character, whitespace included."""
    index: int = -1
    """Position in the token list."""
    partner: int | None = None
    """Index of the balancing delimiter, for Kind.DELIMITER only."""

    @property
    def end(self) -> int:
        return self.start + len(self.text)

    def __repr__(self) -> str:
        p = "" if self.partner is None else f" <->{self.partner}"
        return f"<{self.index}:{self.kind.value} {self.text!r} @{self.line}:{self.col}{p}>"


@dataclass(frozen=True)
class Language:
    name: str
    word: re.Pattern[str]
    """Matched at the current offset to produce one identifier/number/keyword."""
    number: re.Pattern[str]
    """Applied to a whole word to decide IDENTIFIER vs LITERAL."""
    keywords: frozenset[str]
    builtins: frozenset[str] = frozenset()
    literals: frozenset[str] = frozenset()
    """Words that are values: #t, #f, None, True, False."""
    delimiters: dict[str, str] = field(default_factory=dict)
    """open -> close."""
    operators: tuple[str, ...] = ()
    """Matched longest-first, so ,@ wins over , and -> wins over -."""
    punctuation: str = ""
    line_comment: str | None = None
    string_delims: str = '"'

    @property
    def closers(self) -> dict[str, str]:
        return {v: k for k, v in self.delimiters.items()}


def lex(source: str, language: Language) -> list[Token]:
    """Split ``source`` into tokens and resolve delimiter partners."""
    tokens: list[Token] = []
    i = line = col = 0
    n = len(source)

    def emit(text: str, kind: Kind) -> None:
        tokens.append(Token(text, kind, line, col, i))

    while i < n:
        ch = source[i]

        if ch == "\n":
            line, col, i = line + 1, 0, i + 1
            continue
        if ch.isspace():
            col, i = col + 1, i + 1
            continue

        if language.line_comment and source.startswith(language.line_comment, i):
            end = source.find("\n", i)
            end = n if end == -1 else end
            emit(source[i:end], Kind.COMMENT)
            col, i = col + (end - i), end
            continue

        if ch in language.string_delims:
            end = _string_end(source, i, ch)
            emit(source[i:end], Kind.STRING)
            col, i = col + (end - i), end
            continue

        operator = next(
            (op for op in language.operators if source.startswith(op, i)), None
        )
        if operator:
            emit(operator, Kind.OPERATOR)
            col, i = col + len(operator), i + len(operator)
            continue

        if ch in language.delimiters or ch in language.closers:
            emit(ch, Kind.DELIMITER)
            col, i = col + 1, i + 1
            continue

        match = language.word.match(source, i)
        if match and match.end() > i:
            text = match.group()
            kind = (
                Kind.KEYWORD
                if text in language.keywords
                else Kind.BUILTIN
                if text in language.builtins
                else Kind.LITERAL
                if text in language.literals or language.number.fullmatch(text)
                else Kind.IDENTIFIER
            )
            emit(text, kind)
            col, i = col + len(text), match.end()
            continue

        # Anything left is a lone separator or operator character.
        emit(ch, Kind.PUNCTUATION)
        col, i = col + 1, i + 1

    for index, token in enumerate(tokens):
        token.index = index

    _resolve_partners(tokens, language)
    _assert_total_coverage(tokens, source)
    return tokens


def _string_end(source: str, start: int, quote: str) -> int:
    """Offset just past the closing quote, or end of source if never closed."""
    i = start + 1
    while i < len(source):
        if source[i] == "\\":
            i += 2
            continue
        if source[i] == quote:
            return i + 1
        i += 1
    return len(source)


def _resolve_partners(tokens: list[Token], language: Language) -> None:
    """Match delimiters with a stack. A closer that doesn't match the open
    delimiter is left unpartnered rather than popping it, so one stray bracket
    can't cascade into every pair after it."""
    closers = language.closers
    stack: list[Token] = []
    for token in tokens:
        if token.kind is not Kind.DELIMITER:
            continue
        if token.text in language.delimiters:
            stack.append(token)
        elif token.text in closers and stack and stack[-1].text == closers[token.text]:
            opener = stack.pop()
            opener.partner, token.partner = token.index, opener.index


def _assert_total_coverage(tokens: list[Token], source: str) -> None:
    """Every non-whitespace character belongs to exactly one token."""
    covered = bytearray(len(source))
    for token in tokens:
        for offset in range(token.start, token.end):
            covered[offset] = 1
    for offset, ch in enumerate(source):
        if ch.isspace():
            continue
        if not covered[offset]:
            raise AssertionError(
                f"character {offset} ({ch!r}) was not lexed into any token"
            )
