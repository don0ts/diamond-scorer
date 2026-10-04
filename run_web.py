"""Diamond Scorer -- web (browser) entry point.

Runs the exact same FastAPI backend + single-page frontend as the desktop
build, but without the native ``pywebview`` window. Use this when you want to
open Diamond Scorer in an ordinary web browser (local use, a shared workstation,
or a self-hosted deployment behind your own reverse proxy).

SECURITY NOTE
-------------
By default this binds to 127.0.0.1 (localhost only), so the app is reachable
only from the same machine and is NOT exposed on your network. There is no
built-in authentication or access control -- anyone who can reach the bound
address has full read/write access to all data. Do not bind it to a public
interface directly. If you need remote access, put it behind a reverse proxy
(nginx/Caddy) that terminates TLS and enforces authentication.

Usage
-----
    python run_web.py                 # http://127.0.0.1:8000
    PORT=9000 python run_web.py       # choose a port
    HOST=127.0.0.1 PORT=8000 python run_web.py

Then open the printed URL in your browser.
"""
from __future__ import annotations

import os
import webbrowser

import uvicorn

from backend.server import app


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    url = f"http://{host}:{port}"

    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "WARNING: binding to %s exposes Diamond Scorer beyond this machine.\n"
            "         The app has NO authentication -- only do this behind a\n"
            "         trusted reverse proxy that enforces access control.\n" % host
        )

    print(f"\nDiamond Scorer (web mode) is running at: {url}")
    print("Open the URL above in your browser. Press Ctrl+C to stop.\n")

    # Best-effort: pop open the default browser when running locally.
    if os.environ.get("NO_BROWSER") != "1" and host in ("127.0.0.1", "localhost"):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
