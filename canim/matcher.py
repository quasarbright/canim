"""Deciding which source token becomes which destination token.

Three layers, each seeing only what the layer above it didn't claim:

1. the mapping — whatever was written by hand, applied first
2. greedy same-text matching in source order, with delimiter partners forced
3. fade — anything still unclaimed on either side

Layers 2 and 3 have no error cases: every token either finds a same-text
counterpart or fades, mismatched counts included. Everything that raises comes
from an entry in the mapping, which is an assertion rather than a guess.

Imports no manim on purpose — this is where the bugs live, and it should be
debuggable in a REPL.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from .lexer import Kind, Token

Group = tuple[int, ...]
"""Token indices moving as one unit. A single token is a group of one."""

Entry = tuple[tuple[Group, ...], tuple[Group, ...]]
"""One mapping entry, already resolved to token indices: [[from...], [to...]]."""


class Op(Enum):
    MOVE = "move"
    """Same text, new position."""
    MORPH = "morph"
    """Different text. Never inferred — only ever from the mapping."""
    CLONE = "clone"
    """One source group, several destinations."""
    MERGE = "merge"
    """Several source groups converging on one destination."""
    FADE_OUT = "fade out"
    FADE_IN = "fade in"


@dataclass(frozen=True)
class Correspondence:
    op: Op
    src: tuple[Group, ...] = ()
    dst: tuple[Group, ...] = ()
    manual: bool = False
    """Came from the mapping rather than being inferred. Shown in the debug
    labels, because the first question about a wrong arrow is always whether it
    was asserted or guessed."""

    @property
    def src_tokens(self) -> tuple[int, ...]:
        return tuple(i for g in self.src for i in g)

    @property
    def dst_tokens(self) -> tuple[int, ...]:
        return tuple(i for g in self.dst for i in g)


class MappingError(ValueError):
    """An entry in the mapping doesn't make sense."""


def match(
    source: list[Token],
    dest: list[Token],
    entries: list[Entry] | tuple[Entry, ...] = (),
) -> list[Correspondence]:
    state = _State(source, dest)
    for entry in entries:
        state.apply_entry(entry)
    state.greedy()
    state.fade()
    return state.out


@dataclass
class _State:
    source: list[Token]
    dest: list[Token]
    claimed_src: set[int] = field(default_factory=set)
    claimed_dst: set[int] = field(default_factory=set)
    out: list[Correspondence] = field(default_factory=list)

    # --- layer 1 -----------------------------------------------------------

    def apply_entry(self, entry: Entry) -> None:
        frm, to = entry
        self._claim(frm, self.claimed_src, self.source, "source")
        self._claim(to, self.claimed_dst, self.dest, "destination")

        n, m = len(frm), len(to)
        if n and not m:
            self.out.append(Correspondence(Op.FADE_OUT, src=frm, manual=True))
        elif m and not n:
            self.out.append(Correspondence(Op.FADE_IN, dst=to, manual=True))
        elif n == m:
            for a, b in zip(frm, to):
                op = Op.MOVE if self._same_text(a, b) else Op.MORPH
                self.out.append(Correspondence(op, src=(a,), dst=(b,), manual=True))
        elif n == 1:
            self.out.append(Correspondence(Op.CLONE, src=frm, dst=to, manual=True))
        elif m == 1:
            self.out.append(Correspondence(Op.MERGE, src=frm, dst=to, manual=True))
        else:
            raise MappingError(
                f"cannot resolve {n} source group(s) onto {m} destination group(s). "
                "Which source survives changes where the others travel from, so "
                "there is no safe default — split this into separate entries."
            )

    def _claim(self, groups, claimed: set[int], tokens: list[Token], side: str) -> None:
        for group in groups:
            for i in group:
                if i in claimed:
                    raise MappingError(
                        f"{side} token {tokens[i].text!r} (index {i}) is claimed "
                        "by more than one entry"
                    )
                claimed.add(i)

    def _same_text(self, a: Group, b: Group) -> bool:
        return [self.source[i].text for i in a] == [self.dest[j].text for j in b]

    # --- layer 2 -----------------------------------------------------------

    def greedy(self) -> None:
        by_text: dict[str, list[int]] = defaultdict(list)
        for token in self.dest:
            by_text[token.text].append(token.index)

        for token in self.source:
            if token.index in self.claimed_src:
                continue
            j = self._take(by_text, token.text)
            if j is None:
                continue
            self._pair(token.index, j)

            # A matched opener drags its partner along, so a balanced pair in
            # the source can never come out as two halves of different pairs.
            self._force_partner(token, self.dest[j])

    def _force_partner(self, s: Token, d: Token) -> None:
        if s.kind is not Kind.DELIMITER or s.partner is None or d.partner is None:
            return
        # Only openers lead; a closer's partner was handled when it was opened.
        if s.partner < s.index:
            return
        if s.partner in self.claimed_src or d.partner in self.claimed_dst:
            return  # the force loses; that source closer will fade
        self._pair(s.partner, d.partner)

    def _take(self, by_text: dict[str, list[int]], text: str) -> int | None:
        candidates = by_text.get(text)
        while candidates:
            j = candidates.pop(0)
            if j not in self.claimed_dst:
                return j
        return None

    def _pair(self, i: int, j: int) -> None:
        self.claimed_src.add(i)
        self.claimed_dst.add(j)
        self.out.append(Correspondence(Op.MOVE, src=((i,),), dst=((j,),)))

    # --- layer 3 -----------------------------------------------------------

    def fade(self) -> None:
        for token in self.source:
            if token.index not in self.claimed_src:
                self.out.append(Correspondence(Op.FADE_OUT, src=((token.index,),)))
        for token in self.dest:
            if token.index not in self.claimed_dst:
                self.out.append(Correspondence(Op.FADE_IN, dst=((token.index,),)))


# --- reporting -------------------------------------------------------------


def dump(
    source: list[Token],
    dest: list[Token],
    correspondences: list[Correspondence],
) -> str:
    """A plain-text view of the correspondence.

    This is what finds the bugs. A wrong-but-valid correspondence renders a
    perfectly correct final frame, so looking at pixels proves nothing; looking
    at this proves everything.
    """
    where: dict[int, str] = {}
    origin: dict[int, str] = {}

    for c in correspondences:
        mark = "*" if c.manual else " "
        for i in c.src_tokens:
            where[i] = {
                Op.FADE_OUT: "·",
                Op.CLONE: ",".join(str(j) for j in c.dst_tokens),
            }.get(c.op, ",".join(str(j) for j in c.dst_tokens)) + mark
        for j in c.dst_tokens:
            origin[j] = {
                Op.FADE_IN: "·",
            }.get(c.op, ",".join(str(i) for i in c.src_tokens)) + mark

    ops = {}
    for c in correspondences:
        for i in c.src_tokens:
            ops[("s", i)] = c.op
        for j in c.dst_tokens:
            ops[("d", j)] = c.op

    rows = []
    rows.append(f"{'source':<34}{'destination'}")
    rows.append(f"{'-' * 32}  {'-' * 32}")
    for k in range(max(len(source), len(dest))):
        left = right = ""
        if k < len(source):
            t = source[k]
            op = ops.get(("s", k))
            left = f"{k:>3} {t.text!r:<12} -> {where.get(k, '?'):<8} {op.value if op else ''}"
        if k < len(dest):
            t = dest[k]
            op = ops.get(("d", k))
            right = f"{k:>3} {t.text!r:<12} <- {origin.get(k, '?'):<8} {op.value if op else ''}"
        rows.append(f"{left:<44}{right}")
    rows.append("")
    rows.append("* = from the mapping;  · = no counterpart")
    return "\n".join(rows)
