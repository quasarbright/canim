"""Saying which tokens you mean.

A ref is either a bare token string — the first token with that text — or the
result of :meth:`Code.nth` / :meth:`Code.all` / :meth:`Code.partner`. A ref
naming several tokens in a row is a *group*, which moves as one unit.

Resolution is token-level, never a substring search on the source. That is what
keeps ``'a'`` in ``(swap a b)`` from matching the ``a`` inside ``swap``, keeps a
ref from landing inside a string literal or a comment, and lets a multi-token
ref like ``'(lambda (x) (x x))'`` be found however it happens to be line-broken
on screen.
"""

from __future__ import annotations

from dataclasses import dataclass

from .lexer import Kind, Language, Token, lex


class RefError(ValueError):
    """A ref doesn't name anything, or names something impossible."""


@dataclass(frozen=True)
class TokenRef:
    """A contiguous run of tokens in one specific ``Code``."""

    owner: object
    """The Code this came from — used to catch a dest ref in a `from` slot."""
    indices: tuple[int, ...]
    label: str

    def __len__(self) -> int:
        return len(self.indices)

    def __repr__(self) -> str:
        return f"<ref {self.label!r} {list(self.indices)}>"

    @property
    def partner(self) -> TokenRef:
        """The delimiter balancing this one.

        Single delimiters only. A run has no partner, and silently returning
        the first delimiter inside it would be a plausible wrong answer.
        """
        if len(self.indices) != 1:
            raise RefError(
                f"{self.label!r} names {len(self.indices)} tokens; .partner is "
                "only meaningful for a single delimiter"
            )
        token = self.owner.tokens[self.indices[0]]
        if token.kind is not Kind.DELIMITER:
            raise RefError(f"{token.text!r} is not a delimiter, so it has no partner")
        if token.partner is None:
            raise RefError(f"{token.text!r} at index {token.index} is unbalanced")
        return TokenRef(self.owner, (token.partner,), f"{self.label}.partner")


def find_runs(tokens: list[Token], pattern: str, language: Language) -> list[tuple[int, ...]]:
    """Every place ``pattern`` appears as a contiguous run of tokens.

    The pattern is lexed with the same language, so it matches by token text
    rather than by characters — whitespace between tokens is irrelevant.
    """
    wanted = [t.text for t in lex(pattern, language)]
    if not wanted:
        raise RefError(f"{pattern!r} contains no tokens")

    texts = [t.text for t in tokens]
    span = len(wanted)
    return [
        tuple(range(i, i + span))
        for i in range(len(texts) - span + 1)
        if texts[i : i + span] == wanted
    ]


def resolve(ref, code, *, side: str) -> tuple[int, ...]:
    """Turn one ref into token indices, raising with something readable."""
    if isinstance(ref, TokenRef):
        if ref.owner is not code:
            raise RefError(
                f"{ref.label!r} came from a different Code block; it cannot be "
                f"used on the {side} side of an entry"
            )
        return ref.indices
    if isinstance(ref, str):
        return _nth(code, ref, 0).indices
    if isinstance(ref, Token):
        return (ref.index,)
    if isinstance(ref, int):
        return (ref,)
    raise RefError(f"{ref!r} is not a ref")


def _nth(code, pattern: str, index: int) -> TokenRef:
    runs = find_runs(code.tokens, pattern, code.language)
    if not runs:
        raise RefError(
            f"{pattern!r} does not appear in {code.source!r} as a run of tokens"
        )
    try:
        return TokenRef(code, runs[index], f"{pattern}#{index}")
    except IndexError:
        raise RefError(
            f"{pattern!r} appears {len(runs)} time(s); there is no #{index}"
        ) from None


def resolve_entry(entry, source, dest):
    """Turn one authored entry into the index groups the matcher wants.

    ``(["a"], dest.all("a"))`` becomes ``(((2,),), ((5,), (9,)))``. Each ref is
    one group, so counts are counted in refs rather than tokens — a ten-token
    sequence ref is still one thing.
    """
    frm, to = entry
    return (
        tuple(resolve(r, source, side="from") for r in _flatten(frm)),
        tuple(resolve(r, dest, side="to") for r in _flatten(to)),
    )


def resolve_mapping(mapping, source, dest):
    return [resolve_entry(e, source, dest) for e in mapping]


def _flatten(refs):
    """One level, so `[a, dest.all("x")]` works as well as `dest.all("x")`."""
    if isinstance(refs, (str, TokenRef, Token, int)):
        return [refs]
    out = []
    for ref in refs:
        if isinstance(ref, (str, TokenRef, Token, int)):
            out.append(ref)
        else:
            out.extend(ref)
    return out
