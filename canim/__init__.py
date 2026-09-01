"""canim — code transformation animations for manim."""

from .code import Code, Selection
from .debug import correspondence_labels, correspondence_view, debug_block
from .languages import JAVASCRIPT, LISP, PYTHON
from .lexer import Kind, Token, lex
from .matcher import Correspondence, MappingError, Op, dump, match
from .theme import (
    DEFAULT,
    MONOKAI,
    ONE_DARK,
    ONE_DARK_SLATE,
    PASTEL_EVENING,
    SOLARIZED_DARK,
    Theme,
)
from .transform import CodeTransform

__version__ = "0.1.0"

__all__ = [
    "Code",
    "Selection",
    "correspondence_labels",
    "correspondence_view",
    "debug_block",
    "CodeTransform",
    "Correspondence",
    "DEFAULT",
    "MONOKAI",
    "ONE_DARK",
    "ONE_DARK_SLATE",
    "PASTEL_EVENING",
    "SOLARIZED_DARK",
    "Kind",
    "JAVASCRIPT",
    "LISP",
    "MappingError",
    "Op",
    "PYTHON",
    "Theme",
    "Token",
    "dump",
    "lex",
    "match",
]
