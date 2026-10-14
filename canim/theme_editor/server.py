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
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import palette
from .. import theme as theme_module
from ..languages import BY_NAME, resolve
from ..lexer import Kind, lex

APP = Path(__file__).parent / "app"

# Themes that are not canim's. The library ships a handful; everything else
# belongs to whoever is using it, and the editor should still list those
# rather than making you browse to them every time.
WORKSPACE_DIRS: list[Path] = []

# The folder the last save went to, so the next file dialog opens there.
LAST_SAVED_DIR: list[Path | None] = [None]


def workspace_themes() -> list[dict]:
    return [
        {"name": path.name[: -len(theme_module.SUFFIX)], "path": str(path)}
        for directory in WORKSPACE_DIRS
        for path in sorted(directory.glob(f"*{theme_module.SUFFIX}"))
    ]

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


def whole_palette(d: dict) -> dict:
    """Every token color and the chrome that goes with them.

    Chrome comes along because it is not independent: it is built from the
    background and the identifier, and the identifier is one of the things
    just generated. Leaving it out means a theme whose panels and captions
    were pinned to a previous background keep those values and quietly stop
    matching — which reads as the generator producing a broken palette.
    """
    colors = palette.generate_palette(
        d["background"],
        spread=d.get("spread", palette.SPREAD),
        offset=d.get("offset", 0.0),
        chroma=d.get("chroma", palette.CHROMA),
        harmony=d.get("harmony", palette.DEFAULT_HARMONY),
    )
    chrome = palette.generate_chrome(d["background"], colors["identifier"])
    return {**colors, **{f"chrome_{k}": v for k, v in chrome.items()}}


GENERATORS = {
    "palette": whole_palette,
    "chrome": lambda d: {
        f"chrome_{k}": v
        for k, v in palette.generate_chrome(d["background"], d["identifier"]).items()
    },
    "identifier": lambda d: {"identifier": palette.generate_identifier(d["background"])},
    "keyword": lambda d: {"keyword": palette.generate_keyword(d["background"])},
    "comment": lambda d: {"comment": palette.generate_comment(d["background"])},
    # One row's button. Roles that share a color by convention resolve to
    # whichever one owns it, so `operator` comes back as the keyword's.
    "role": lambda d: {d["role"]: palette.generate_role(d["background"], d["role"])},
}


def start_dir() -> Path:
    """Where a file dialog opens: the folder last saved to, then your themes.

    Never canim's own themes directory. Those ship with the library and are
    not somewhere a user's theme belongs.
    """
    for directory in (LAST_SAVED_DIR[0], *WORKSPACE_DIRS):
        if directory is not None and directory.is_dir():
            return directory
    return Path.cwd()


def choose_file(save: bool, suggested: str = "") -> str | None:
    """A real file dialog, since a browser cannot offer a filesystem path.

    Shelled out to AppleScript rather than faked with a text field. Returns
    None when the dialog is cancelled, which is not an error.
    """
    themes = str(start_dir())
    if save:
        script = (
            f'set d to POSIX file "{themes}" as alias\n'
            f'set f to choose file name with prompt "Save theme as"'
            f' default name "{suggested}" default location d\n'
            "POSIX path of f"
        )
    else:
        script = (
            f'set d to POSIX file "{themes}" as alias\n'
            f'set f to choose file with prompt "Open a theme"'
            f' default location d of type {{"json"}}\n'
            "POSIX path of f"
        )
    done = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True
    )
    if done.returncode != 0:
        return None  # cancelled
    return done.stdout.strip() or None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP), **kwargs)

    def log_message(self, *args):  # quiet; this runs in a terminal you are using
        pass

    def end_headers(self) -> None:
        # No caching. This serves files you are editing, and a browser holding
        # on to a stale app.js looks exactly like a bug in the code you just
        # changed — which is what it looked like the first time it happened.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

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

    def _send_index(self) -> None:
        """index.html with the asset URLs stamped by modification time.

        `Cache-Control: no-store` is not enough on its own. The very first
        response for `app.js` went out without cache headers, so Chrome cached
        it heuristically and stopped revalidating — it never asks again, so it
        never sees the header telling it not to. Stamping the URL means an
        edited file is a different URL and a stale entry cannot be reused.
        """
        html = (APP / "index.html").read_text()
        for asset in ("app.js", "app.css"):
            stamp = int((APP / asset).stat().st_mtime)
            html = html.replace(f'"{asset}"', f'"{asset}?v={stamp}"')
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            return self._send_index()
        if url.path == "/api/themes":
            return self._send(
                {
                    "names": theme_module.discover(),
                    "workspace": workspace_themes(),
                    "directory": str(theme_module.THEMES_DIR),
                    # One entry per language; `js` and `hs` are aliases.
                    "languages": sorted({lang.name for lang in BY_NAME.values()}),
                "harmonies": sorted(palette.HARMONY),
                "defaults": {
                    "harmony": palette.DEFAULT_HARMONY,
                    "spread": palette.SPREAD,
                    "chroma": palette.CHROMA,
                },
                }
            )
        if url.path == "/api/theme":
            try:
                path = self._checked_path(query["path"][0])
                return self._send({
                    "path": str(path),
                    "theme": theme_module.to_dict(theme_module.open(path)),
                    # Whether this is one of the themes canim ships. The editor
                    # will not let Save write back over one of those.
                    "builtin": path.parent == theme_module.THEMES_DIR,
                })
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
            if url.path == "/api/pick":
                chosen = choose_file(
                    save=bool(data.get("save")), suggested=data.get("suggested", "")
                )
                return self._send({"path": chosen})
            if url.path == "/api/theme":
                path = self._checked_path(data["path"])
                if path.parent == theme_module.THEMES_DIR:
                    raise ValueError(
                        "that is canim's own themes folder; save your theme somewhere else"
                    )
                theme_module.save(theme_module.from_dict(data["theme"]), path)
                LAST_SAVED_DIR[0] = path.parent
                return self._send({"path": str(path)})
        except (KeyError, OSError, ValueError) as error:
            return self._send({"error": str(error)}, 400)
        self._send({"error": f"no route for {url.path}"}, 404)


def serve(port: int = 8765, workspace: list[Path] | None = None) -> None:
    WORKSPACE_DIRS[:] = [d for d in (workspace or []) if d.is_dir()]
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"canim theme editor — http://127.0.0.1:{port}")
    print(f"built-in themes in {theme_module.THEMES_DIR}")
    for directory in WORKSPACE_DIRS:
        print(f"also listing {directory}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
