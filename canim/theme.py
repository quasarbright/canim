"""Token colors, plus the few non-token colors a scene needs around them.

One Dark, minus its background — the video keeps its own darker navy. Only one
theme for now; the shape is here so adding others later doesn't touch anything
else.

Beyond the per-Kind colors there are the colors that aren't syntax: panel fills
and their borders, de-emphasized text, the red for "this is the bad option".
Scenes were carrying those as literals, which meant a new theme would leave
them behind. They live here now. Each one defaults to a value mixed out of the
background, so a new theme gets chrome that at least belongs to its palette
without having to name seven more hexes; a theme that cares can pin them.

Pinning is worth it whenever the derivation stops holding a relationship the
scenes were built against. Mixing toward the foreground works on a near-black
background and stops working as the background lightens or saturates: on a
light ground the captions come out too faint to read, and on a saturated one
the panels wash gray instead of staying in the palette. Both cases want the
background's own hue lifted by lightness instead, which is what the generators
in `palette.py` produce.

The palettes themselves are not here. They live one-per-file in `themes/` as
`.theme.json`, so the editor and the videos read the same bytes — see `open`,
`save` and `discover` below.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .lexer import Kind

THEMES_DIR = Path(__file__).parent / "themes"
SUFFIX = ".theme.json"

# How far each derivable chrome field sits from the background, toward the
# identifier color.
DERIVED_FROM_BACKGROUND = {
    "surface": 0.06,
    "surface_stroke": 0.22,
    "frame": 0.05,
    "frame_stroke": 0.28,
    "muted": 0.45,
    "subtle": 0.55,
}
CHROME_FIELDS = (*DERIVED_FROM_BACKGROUND, "danger")
DEFAULT_DANGER = "#e06c75"


def _mix(a: str, b: str, t: float) -> str:
    """Blend two hex colors, t=0 giving all `a`."""
    ar, ag, ab = (int(a[i : i + 2], 16) for i in (1, 3, 5))
    br, bg, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (
        round(ar + (br - ar) * t),
        round(ag + (bg - ag) * t),
        round(ab + (bb - ab) * t),
    )


@dataclass(frozen=True)
class Theme:
    name: str
    colors: dict[Kind, str]
    background: str

    # Non-syntax colors. None means "derive from the background" — see
    # __post_init__ for the mix amounts.
    surface: str | None = None  # small boxes: token chips
    surface_stroke: str | None = None
    frame: str | None = None  # large boxes: the labeled frames around groups
    frame_stroke: str | None = None
    muted: str | None = None  # captions — quietest readable text
    subtle: str | None = None  # arrows, connectors — structure, not text
    danger: str | None = None  # the "no" red; no Kind owns it

    def __post_init__(self) -> None:
        fg = self.colors[Kind.IDENTIFIER]
        # Which chrome the theme named for itself, recorded before the rest is
        # filled in. Afterwards every field holds a color and there is no way
        # to tell the two apart, which round-tripping a theme through a file
        # needs to know: a derived field must not be written back as if it had
        # been chosen.
        pinned = {f for f in CHROME_FIELDS if getattr(self, f) is not None}
        object.__setattr__(self, "pinned", frozenset(pinned))
        for name, amount in DERIVED_FROM_BACKGROUND.items():
            if getattr(self, name) is None:
                object.__setattr__(self, name, _mix(self.background, fg, amount))
        if self.danger is None:
            object.__setattr__(self, "danger", DEFAULT_DANGER)

    def color(self, kind: Kind) -> str:
        return self.colors[kind]

    def __deepcopy__(self, memo):
        # Immutable and shared by every block; see Language.__deepcopy__.
        return self


def to_dict(theme: Theme) -> dict[str, str]:
    """A theme as the flat mapping a `.theme.json` file holds.

    Flat because a theme is a list of colors and nothing else; nesting the
    kinds under `colors` bought nothing and made every reader walk a level.
    Chrome is prefixed rather than nested for the same reason, and only what
    the theme pinned is written — a derived field left in the file would
    freeze a value that is supposed to follow the background.
    """
    data = {"name": theme.name, "background": theme.background}
    data.update({kind.value: theme.colors[kind] for kind in Kind})
    data.update({f"chrome_{f}": getattr(theme, f) for f in sorted(theme.pinned)})
    return data


def _color(data: dict[str, str], key: str) -> str:
    """One color out of a theme file, checked.

    Worth checking rather than trusting: a three-digit hex or a stray name
    reaches the color math as a slice of the wrong length and fails several
    calls later with something like `invalid literal for int()`, which says
    nothing about which field is wrong.
    """
    try:
        value = data[key]
    except KeyError:
        raise ValueError(f"no color for {key!r}") from None
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(value)):
        raise ValueError(f"{key} must be a 6-digit hex color, got {value!r}")
    return value.lower()


def from_dict(data: dict[str, str]) -> Theme:
    chrome = {
        f: _color(data, f"chrome_{f}")
        for f in CHROME_FIELDS
        if f"chrome_{f}" in data
    }
    return Theme(
        name=str(data.get("name", "untitled")),
        background=_color(data, "background"),
        colors={kind: _color(data, kind.value) for kind in Kind},
        **chrome,
    )


def path_for(name_or_path: str | Path) -> Path:
    """Where a theme lives. A bare name means one of canim's own."""
    path = Path(name_or_path)
    if path.suffix or path.parent != Path("."):
        return path
    return THEMES_DIR / f"{name_or_path}{SUFFIX}"


def open(name_or_path: str | Path) -> Theme:  # noqa: A001 — the editor calls it Open
    """Read a theme by name or by path.

    `Path.read_text` rather than the builtin `open`, which this shadows.
    """
    path = path_for(name_or_path)
    if not path.exists() and path.parent == THEMES_DIR:
        # A bare name that canim does not ship. Worth naming what it does,
        # because the raw error points inside the installed package and reads
        # as canim being broken rather than as the name being someone else's.
        # This is what a theme moving out of the library looks like from here.
        raise FileNotFoundError(
            f"canim ships no theme named {str(name_or_path)!r}. "
            f"Its own are {', '.join(discover())}. "
            f"For any other theme, pass a path to its {SUFFIX} file."
        )
    return from_dict(json.loads(path.read_text()))


def save(theme: Theme, name_or_path: str | Path | None = None) -> Path:
    """Write a theme, defaulting to canim's own directory under its name."""
    path = path_for(name_or_path if name_or_path is not None else theme.name)
    if not path.name.endswith(SUFFIX):
        raise ValueError(f"a theme file must end in {SUFFIX}: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(theme), indent=2) + "\n")
    return path


def discover() -> list[str]:
    """Every theme canim ships, by name."""
    if not THEMES_DIR.exists():
        return []
    return sorted(p.name[: -len(SUFFIX)] for p in THEMES_DIR.glob(f"*{SUFFIX}"))


# The themes canim ships, as objects. A caller should never have to know where
# they live on disk: `theme.ONE_DARK` rather than a path, and `theme.open` with
# a path only for themes that are not the library's.
ONE_DARK = open("one-dark")
ONE_DARK_SLATE = open("one-dark-slate")
PASTEL_EVENING = open("pastel-evening")
MONOKAI = open("monokai")
SOLARIZED_DARK = open("solarized-dark")

BUILT_IN = {
    t.name: t
    for t in (ONE_DARK, ONE_DARK_SLATE, PASTEL_EVENING, MONOKAI, SOLARIZED_DARK)
}

# What a `Code` block gets when nobody says otherwise. A video that wants a
# different palette opens its own and passes it in, rather than reassigning
# this — see `2026/macros/main.py`.
DEFAULT = ONE_DARK_SLATE

# Set once here so every scene and every Code block agrees.
FONT = "Monaco"
FONT_SIZE = 28
LINE_SPACING = 0.7
