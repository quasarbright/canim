"""Generate the theme editor page.

The samples are lexed here, by the same lexer the video uses, and baked into
the page as a flat list of (text, kind) segments. The page itself has no lexer
— it only paints spans — so what you see in the browser is what a `Code` block
would paint, rather than a second opinion about what a token is.

    python canim/theme_editor/build.py
"""

from __future__ import annotations

import json
from pathlib import Path

from canim.languages import JAVASCRIPT, LISP, PYTHON
from canim.lexer import Kind, lex
from canim.theme import ONE_DARK, Theme

HERE = Path(__file__).parent

SAMPLES = [
    (
        "python",
        PYTHON,
        '''\
import ast

def state_machine(source: str) -> type:
    # every branch of the parser lands somewhere
    tree = ast.parse(source)
    if tree is None or len(tree.body) == 0:
        raise ValueError(f"nothing to build: {source!r}")
    return ClassDef(name="VendingMachine", bases=[], body=[...])
''',
    ),
    (
        "javascript",
        JAVASCRIPT,
        """\
// every branch of the parser lands somewhere
const stateMachine = (source) => {
  const tree = JSON.parse(source);
  if (tree === null || tree.states.length === 0) {
    throw new Error(`nothing to build: ${source}`);
  }
  return { name: "VendingMachine", states: [...tree.states], count: 42 };
};
""",
    ),
    (
        "lisp",
        LISP,
        """\
; swap two places without colliding with the use site
(defmacro swap (x y)
  (let ((tmp (gensym)))
    `(let ((,tmp ,x))
       (setf ,x ,y
             ,y ,tmp))))

(defvar a 1)
(swap a b)          ; => "done", #t, 42
""",
    ),
]

# Themes to start from. One Dark comes out of canim so it cannot drift; the
# rest are here because they were worth keeping.
EXTRA_PRESETS = {
    # One Dark's tokens on a lighter slate ground. Chrome is left to derive:
    # the values ONE_DARK pins are tuned to its near-black #0e0f16 and land
    # *darker* than this background, which would sink the panels instead of
    # lifting them.
    "one-dark slate": dict(
        background="#22253a", fg="#abb2bf", keyword="#c678dd", builtin="#56b6c2",
        literal="#d19a66", string="#98c379", comment="#5c6370",
    ),
    # After a "Pastel Evening" stripe palette: charcoal ground, with the
    # lavender-gray as the foreground and the four pastels taking a role each.
    # The comment is a dimmed lavender rather than one of the stripes — the
    # source has no fifth quiet color, and the dark stripe is the background.
    "pastel evening": dict(
        background="#262a38", fg="#b3b4c4", keyword="#e0898f", builtin="#7cb2f0",
        literal="#e8bc84", string="#7fe2a0", comment="#8286a0",
    ),
    # Pastel and vibrant pull against each other — pastel wants lightness,
    # vibrant wants chroma — so this takes both: every token is up around 70%
    # lightness *and* near-full saturation, which stays pastel while reading
    # as neon. The near-black plum background is what makes it work; on the
    # lighter tinted backgrounds the other pastels use, colors this saturated
    # lose their glow. Every token clears 8:1 against it and the comment
    # clears 5:1.
    "vivid purple": dict(
        background="#2b0439", fg="#f2ebf4", keyword="#ff85d2", builtin="#66d9ff",
        literal="#ffe066", string="#6ff6c4", comment="#a872b6",
    ),
    # The same palette on a plum ground.
    "vivid magenta": dict(
        background="#420431", fg="#f2ebf4", keyword="#ff85d2", builtin="#66d9ff",
        literal="#ffe066", string="#6ff6c4", comment="#a872b6",
    ),
    # Started from a front/back/mono/vivid/alert stripe palette and then took
    # its own direction in the editor: rose keyword, aqua builtin, amber
    # literal, green string, on a much deeper ground than the original.
    "vivid blue": dict(
        background="#08004d", fg="#c5d8f5", keyword="#ee5382", builtin="#2fe5ee",
        literal="#f4a65d", string="#70ff88", comment="#5896b6",
    ),
    # Warm all the way through — the accents stay in the red-to-yellow arc the
    # background sits at one end of, with the green string as the only thing
    # outside it.
    "forest fire": dict(
        background="#3f0303", fg="#f0d8d8", keyword="#ff5c5c", builtin="#fba52d",
        literal="#ffff00", string="#21b024", comment="#b56969",
    ),
    "TGC green for me": dict(
        background="#022210", fg="#e1f4ea", keyword="#f85dcf", builtin="#02ca8e",
        literal="#9950f2", string="#53f9d8", comment="#219152",
    ),
    # Built from five colors, with the roles assigned the way "TGC green for
    # me" assigns them: pink keyword, the background's own family for builtin
    # with a quieter version of it for comment, and the odd colour out — the
    # neon green — on strings.
    #
    # Two roles the five do not cover. `literal` is a warm gold: everything
    # given is blue, green or pink, and numbers need to leave that family to
    # be findable. `comment` is builtin's hue desaturated rather than darkened
    # — on a background this dark there is no room below #399af3 to go dimmer
    # and still clear 4.5:1, so it goes quieter instead.
    "TGC blue for me": dict(
        background="#0f0396", fg="#b6d8fb", keyword="#f55cc4", builtin="#399af3",
        literal="#f8ce59", string="#1aff47", comment="#7296c0",
    ),
    # Orange keyword, green builtin, pure yellow literal, aqua string.
    "tree frog": dict(
        background="#022210", fg="#e1f4ea", keyword="#f57724", builtin="#2fd075",
        literal="#fbff00", string="#2edcff", comment="#219152",
    ),
}

# Themes that name every kind rather than going through `spread`, which
# assumes the six-color shape the video uses — operators sharing the keyword's
# color, delimiters and punctuation sharing the foreground's. A theme that
# splits those needs to say so itself.
FULL_PRESETS = {
    # Operators break away from the keyword here — magenta against a teal
    # keyword — which is why this cannot go through `spread`.
    "marine": {
        "background": "#022c26",
        "colors": {
            "identifier": "#e1f4ea",
            "keyword": "#28c8b3",
            "builtin": "#2edcff",
            "operator": "#e147c0",
            "literal": "#d4d638",
            "delimiter": "#e1f4ea",
            "punctuation": "#e1f4ea",
            "string": "#22d325",
            "comment": "#186d61",
        },
    },
    # Mike's, from the editor. Operators get their own teal against a
    # magenta-family keyword, and the delimiters sit a shade off the
    # identifiers.
    "TheGrayCuber Plum": {
        "background": "#420431",
        "colors": {
            "identifier": "#f5cce9",
            "keyword": "#ee2bba",
            "builtin": "#f95353",
            "operator": "#23dec2",
            "literal": "#f4a152",
            "delimiter": "#e8c4de",
            "punctuation": "#e8c4de",
            "string": "#f4d952",
            "comment": "#c27085",
        },
    },
}

# Themes whose chrome should not be derived. On a background this light the
# mix toward the foreground does not lift far enough — captions land at 3.2:1
# — so the quiet blue from the palette does that job instead.
PINNED_CHROME = {
    # Regenerated for this background: the values that came with it were a
    # green theme's, tuned to #022210, and would have sat off-hue on a teal.
    "marine": {
        "surface": "#083f38", "surface_stroke": "#1f6b60",
        "frame": "#053831", "frame_stroke": "#27776b",
        "muted": "#74beb3", "subtle": "#68b1a6", "danger": "#f67283",
    },
    "TGC green for me": {
        "surface": "#08361c", "surface_stroke": "#1e623c",
        "frame": "#052e17", "frame_stroke": "#266e46",
        "muted": "#74be94", "subtle": "#68b188", "danger": "#ec6565",
    },
    "TGC blue for me": {
        "surface": "#1c10a2", "surface_stroke": "#3f34c1",
        "frame": "#170b9d", "frame_stroke": "#4e44c5",
        "muted": "#a9a5d5", "subtle": "#8f8bc3", "danger": "#f97ba3",
    },
    # Both purples moved onto lighter grounds than the near-black they were
    # tuned for, where the derivation no longer lifts far enough — it puts
    # captions at 3.6:1. Surfaces are the background's own hue lifted in
    # lightness; muted and subtle are raised until they clear 6:1 and 4.5:1.
    "vivid purple": {
        "surface": "#3a0b4b", "surface_stroke": "#5f2574",
        "frame": "#340844", "frame_stroke": "#6a2d80",
        "muted": "#b586c6", "subtle": "#a16db4", "danger": "#ff7a91",
    },
    "vivid magenta": {
        "surface": "#540c40", "surface_stroke": "#7c2664",
        "frame": "#4d093a", "frame_stroke": "#872f6f",
        "muted": "#c88bb7", "subtle": "#b672a3", "danger": "#ff7a91",
    },
    "pastel evening": {
        "surface": "#2f3548", "surface_stroke": "#484f68",
        "frame": "#2b3043", "frame_stroke": "#515973",
        "muted": "#9399ae", "subtle": "#83899d", "danger": "#e0898f",
    },
    # Regenerated for the darker background this moved to. The surfaces are
    # its own hue lifted in lightness; `muted` and `subtle` are raised until
    # they clear 6:1 and 4.5:1, which the plain derivation does not manage
    # here — it lands captions at 3.3:1.
    "vivid blue": {
        "surface": "#11085f", "surface_stroke": "#2c2287",
        "frame": "#0d0558", "frame_stroke": "#352b93",
        "muted": "#918bc8", "subtle": "#7c75b8", "danger": "#f97ba3",
    },
    # Surfaces and frames are the background's own hue lifted in lightness, so
    # panels sit on the field rather than turning gray on it. `danger` is the
    # exception to deriving from the background: it stays in the alarm band
    # — red, else hot pink, else orange-red — because a green or yellow "bad
    # option" marker is not a warning however well it contrasts.
    "forest fire": {
        "surface": "#610f0f", "surface_stroke": "#882b2b",
        "frame": "#5b0b0b", "frame_stroke": "#933434",
        "muted": "#cd9595", "subtle": "#bb7c7c", "danger": "#ff5c5c",
    },
    "TheGrayCuber Plum": {
        "surface": "#540c40", "surface_stroke": "#7c2664",
        "frame": "#4d093a", "frame_stroke": "#872f6f",
        "muted": "#c88bb7", "subtle": "#b672a3", "danger": "#f95353",
    },
    "tree frog": {
        "surface": "#08361c", "surface_stroke": "#1e623c",
        "frame": "#052e17", "frame_stroke": "#266e46",
        "muted": "#74be94", "subtle": "#68b188", "danger": "#ec6565",
    },
}

# Which chrome fields are derived rather than named, and by how much. Kept in
# step with `Theme.__post_init__` so the page can show what a theme that has
# not pinned them will actually get.
DERIVED = [
    ("surface", 0.06),
    ("surface_stroke", 0.22),
    ("frame", 0.05),
    ("frame_stroke", 0.28),
    ("muted", 0.45),
    ("subtle", 0.55),
]


def segments(source: str, language) -> list[dict]:
    """Every character of the source, as spans with a kind or without one."""
    out: list[dict] = []
    cursor = 0
    for token in lex(source, language):
        if token.start > cursor:
            out.append({"text": source[cursor : token.start], "kind": None})
        out.append({"text": token.text, "kind": token.kind.value})
        cursor = token.end
    if cursor < len(source):
        out.append({"text": source[cursor:], "kind": None})
    return out


def as_preset(theme: Theme) -> dict:
    preset = {
        "background": theme.background,
        "colors": {kind.value: color for kind, color in theme.colors.items()},
    }
    # Only what the theme pinned; anything matching the derivation is left out
    # so the page shows it as derived, the way `theme.py` does.
    chrome = {}
    for field, amount in DERIVED:
        if getattr(theme, field) != mix(theme.background, theme.colors[Kind.IDENTIFIER], amount):
            chrome[field] = getattr(theme, field)
    if theme.danger != "#e06c75":
        chrome["danger"] = theme.danger
    preset["chrome"] = chrome
    return preset


def mix(a: str, b: str, t: float) -> str:
    ar, ag, ab = (int(a[i : i + 2], 16) for i in (1, 3, 5))
    br, bg, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (
        round(ar + (br - ar) * t),
        round(ag + (bg - ag) * t),
        round(ab + (bb - ab) * t),
    )


def spread(name: str, background: str, *, fg: str, keyword: str, builtin: str,
           literal: str, string: str, comment: str) -> dict:
    """A six-color palette as the nine kinds, the way the video maps them."""
    return {
        "background": background,
        "colors": {
            Kind.IDENTIFIER.value: fg,
            Kind.DELIMITER.value: fg,
            Kind.PUNCTUATION.value: fg,
            Kind.KEYWORD.value: keyword,
            Kind.OPERATOR.value: keyword,
            Kind.BUILTIN.value: builtin,
            Kind.LITERAL.value: literal,
            Kind.STRING.value: string,
            Kind.COMMENT.value: comment,
        },
        "chrome": PINNED_CHROME.get(name, {}),
    }


def main() -> None:
    data = {
        "kinds": [kind.value for kind in Kind],
        "derived": {field: amount for field, amount in DERIVED},
        "samples": [
            {"name": name, "segments": segments(source, language)}
            for name, language, source in SAMPLES
        ],
        "presets": {
            ONE_DARK.name: as_preset(ONE_DARK),
            **{name: spread(name, **kw) for name, kw in EXTRA_PRESETS.items()},
            **{
                name: {**spec, "chrome": PINNED_CHROME.get(name, {})}
                for name, spec in FULL_PRESETS.items()
            },
        },
    }

    template = (HERE / "template.html").read_text()
    page = template.replace("/*__DATA__*/null", json.dumps(data, indent=2))
    (HERE / "index.html").write_text(page)
    print(f"wrote {HERE / 'index.html'} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
