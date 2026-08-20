"""    python -m canim.theme_editor [--port 8765] [--no-open]"""

import argparse
import threading
import webbrowser

from .server import serve

parser = argparse.ArgumentParser(prog="canim.theme_editor", description=__doc__)
parser.add_argument("--port", type=int, default=8765)
parser.add_argument("--no-open", action="store_true", help="do not open a browser")
args = parser.parse_args()

if not args.no_open:
    url = f"http://127.0.0.1:{args.port}"
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()

serve(args.port)
