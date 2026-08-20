"""A local API for the theme editor.

The point of running a server at all is that canim's own code answers the
questions. The page never lexes and never does color math — it asks, and gets
back exactly what a render would produce. A browser-side copy of either would
be a second opinion that drifts, which is the problem the themes-in-two-places
setup already had.

Colors still update instantly in the page, because that is CSS. Only the
things that need canim — lexing, generating, the warnings — cross the wire,
and a localhost round trip is fast enough to debounce behind a drag.
"""

from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import palette
from .. import theme as theme_module
from ..languages import BY_NAME, resolve
from ..lexer import Kind, lex

APP = Path(__file__).parent / "app"

# What counts as worth a warning. Contrast is against the background and
# decides legibility; separation is between two token colors and decides
# whether you can tell them apart. Both matter and neither implies the other.
CONTRAST_BAD = 3.0
CONTRAST_WARN = 4.5
SEPARATION_WARN = 1.0  # `palette.separation` is scored against its own threshold

# Roles that share a color on purpose. Every theme in the repo does these, so
# reporting them would bury the collisions that matter. Checking for identical
# hexes instead is not enough — it lets a keyword that happens to equal the
# builtin through as if it were a convention.
CONVENTIONAL = {
    frozenset({"keyword", "operator"}),
    frozenset({"identifier", "delimiter"}),
    frozenset({"identifier", "punctuation"}),
    frozenset({"delimiter", "punctuation"}),
}


def segments(source: str, language_name: str) -> list[dict]:
    """Source as spans carrying a kind, whitespace included."""
    language = resolve(language_name)
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


def analyze(data: dict) -> dict:
    """Contrast, separation, and what is worth flagging in the UI."""
    background = data["background"]
    roles = [k.value for k in Kind]
    contrast = {r: palette.contrast(background, data[r]) for r in roles}
    contrast["background"] = 1.0

    warnings: dict[str, list[str]] = {}

    def flag(field: str, message: str) -> None:
        warnings.setdefault(field, []).append(message)

    for role in roles:
        ratio = contrast[role]
        if ratio < CONTRAST_BAD:
            flag(role, f"{ratio:.1f}:1 against the background — too faint to read")
        elif ratio < CONTRAST_WARN:
            flag(role, f"{ratio:.1f}:1 against the background — under 4.5:1")

    for i, a in enumerate(roles):
        for b in roles[i + 1 :]:
            if frozenset({a, b}) in CONVENTIONAL:
                continue
            if palette.separation(data[a], data[b]) < SEPARATION_WARN:
                flag(a, f"hard to tell apart from {b}")
                flag(b, f"hard to tell apart from {a}")

    for field in theme_module.CHROME_FIELDS:
        key = f"chrome_{field}"
        if key not in data:
            continue
        if field in ("muted", "subtle", "danger"):
            ratio = palette.contrast(background, data[key])
            contrast[key] = ratio
            if ratio < CONTRAST_WARN:
                flag(key, f"{ratio:.1f}:1 against the background — under 4.5:1")

    # Where each color sits in OKLCH, so the hue map can be drawn without a
    # second implementation of the color math in the page.
    oklch = {r: palette.to_oklch(data[r]) for r in roles}
    oklch["background"] = palette.to_oklch(background)

    return {"contrast": contrast, "warnings": warnings, "oklch": oklch}


GENERATORS = {
    "palette": lambda d: palette.generate_palette(
        d["background"],
        spread=d.get("spread", palette.SPREAD),
        offset=d.get("offset", 0.0),
        chroma=d.get("chroma", palette.CHROMA),
    ),
    "chrome": lambda d: {
        f"chrome_{k}": v
        for k, v in palette.generate_chrome(d["background"], d["identifier"]).items()
    },
    "identifier": lambda d: {"identifier": palette.generate_identifier(d["background"])},
    "keyword": lambda d: {"keyword": palette.generate_keyword(d["background"])},
    "comment": lambda d: {"comment": palette.generate_comment(d["background"])},
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP), **kwargs)

    def log_message(self, *args):  # quiet; this runs in a terminal you are using
        pass

    # --- plumbing ----------------------------------------------------------

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        return json.loads(self.rfile.read(int(self.headers["Content-Length"] or 0)))

    def _checked_path(self, raw: str) -> Path:
        """A theme path, or a refusal.

        The only rule is the extension. The editor is allowed to open and save
        wherever you point it — but a tool that writes files on request should
        not be able to write over something that is not its own.
        """
        # Resolve first: a bare name means one of canim's own themes, and only
        # then does the suffix rule apply — otherwise "marine" gets refused for
        # not being a filename.
        path = theme_module.path_for(Path(raw).expanduser())
        if not path.name.endswith(theme_module.SUFFIX):
            raise ValueError(f"only {theme_module.SUFFIX} files: {path.name}")
        return path

    # --- routes ------------------------------------------------------------

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/api/themes":
            return self._send(
                {
                    "names": theme_module.discover(),
                    "directory": str(theme_module.THEMES_DIR),
                    "languages": sorted(BY_NAME),
                }
            )
        if url.path == "/api/theme":
            try:
                path = self._checked_path(query["path"][0])
                return self._send(
                    {"path": str(path), "theme": theme_module.to_dict(theme_module.open(path))}
                )
            except (KeyError, OSError, ValueError) as error:
                return self._send({"error": str(error)}, 400)
        return super().do_GET()

    def do_POST(self) -> None:
        url = urlparse(self.path)
        try:
            data = self._body()
            if url.path == "/api/lex":
                return self._send(
                    {"segments": segments(data["source"], data["language"])}
                )
            if url.path == "/api/analyze":
                return self._send(analyze(data))
            if url.path == "/api/simulate":
                return self._send(
                    {
                        key: palette.simulate(value, data["kind"])
                        for key, value in data["theme"].items()
                        if isinstance(value, str) and value.startswith("#")
                    }
                )
            if url.path.startswith("/api/generate/"):
                which = url.path.rsplit("/", 1)[-1]
                return self._send(GENERATORS[which](data))
            if url.path == "/api/theme":
                path = self._checked_path(data["path"])
                theme_module.save(theme_module.from_dict(data["theme"]), path)
                return self._send({"path": str(path)})
        except (KeyError, OSError, ValueError) as error:
            return self._send({"error": str(error)}, 400)
        self._send({"error": f"no route for {url.path}"}, 404)


def serve(port: int = 8765) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"canim theme editor — http://127.0.0.1:{port}")
    print(f"themes in {theme_module.THEMES_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
