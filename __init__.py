"""canim — code transformation animations for manim."""

from .code import Code
from .debug import correspondence_labels, correspondence_view, debug_block
from .languages import LISP, PYTHON
from .lexer import Kind, Token, lex
from .matcher import Correspondence, MappingError, Op, dump, match
from .theme import DEFAULT, ONE_DARK, Theme
from .transform import CodeTransform

__version__ = "0.1.0"

__all__ = [
    "Code",
    "correspondence_labels",
    "correspondence_view",
    "debug_block",
    "CodeTransform",
    "Correspondence",
    "DEFAULT",
    "Kind",
    "LISP",
    "MappingError",
    "ONE_DARK",
    "Op",
    "PYTHON",
    "Theme",
    "Token",
    "dump",
    "lex",
    "match",
]
