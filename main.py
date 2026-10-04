"""Diamond Scorer -- desktop entry point.

Starts the FastAPI backend on a local-only port (127.0.0.1) and opens it inside
a native desktop window via ``pywebview``. If pywebview is not installed (e.g.
headless development), it falls back to serving only and printing the URL so it
can be opened in a browser.

The server binds to 127.0.0.1 exclusively -- it is never exposed on the network.
"""
from __future__ import annotations

import socket
import threading
import time

import uvicorn

from backend.server import app

HOST = "127.0.0.1"


class JsApi:
    """Bridge exposed to the web layer inside the native desktop window.

    Its main job is a reliable *Save As* flow for report exports. Writing files
    directly from the packaged backend can fail (read-only install dir, no
    obvious output location for the user). Routing exports through the native
    save dialog guarantees a user-chosen, writable destination and lets us open
    the containing folder afterwards.
    """

    def __init__(self) -> None:
        self.window = None

    def _build(self, game_id: int, kind: str):
        from backend import reports
        if kind == "pdf":
            return reports.build_report_pdf(int(game_id)), "pdf"
        return reports.build_report_html(int(game_id)).encode("utf-8"), "html"

    def save_report(self, game_id, kind="pdf"):
        """Build a report and prompt the user for a save location.

        Returns a dict the JS layer inspects: ``{ok, path}`` on success,
        ``{ok:False, cancelled:True}`` if the dialog was dismissed, or
        ``{ok:False, error:...}`` on failure.
        """
        import os
        try:
            data, ext = self._build(game_id, kind)
        except Exception as exc:  # pragma: no cover - runtime guard
            return {"ok": False, "error": "Could not build report: %s" % exc}
        try:
            import webview
            default = "game_%s_report.%s" % (game_id, ext)
            ftypes = (("PDF file (*.pdf)",) if ext == "pdf"
                      else ("HTML file (*.html)",))
            res = self.window.create_file_dialog(
                webview.SAVE_DIALOG,
                directory=os.path.join(os.path.expanduser("~"), "Documents"),
                save_filename=default,
                file_types=ftypes,
            )
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": "Save dialog failed: %s" % exc}
        if not res:
            return {"ok": False, "cancelled": True}
        path = res if isinstance(res, str) else res[0]
        if "." not in os.path.basename(path):
            path = "%s.%s" % (path, ext)
        try:
            with open(path, "wb") as fh:
                fh.write(data)
        except Exception as exc:
            return {"ok": False, "error": "Could not write file: %s" % exc}
        return {"ok": True, "path": path}

    def open_folder(self, path):
        """Reveal a saved file's containing folder in the OS file manager."""
        import os
        import subprocess
        import sys
        try:
            folder = os.path.dirname(path) or path
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
            return {"ok": True}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": str(exc)}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _run_server(port: int) -> None:
    uvicorn.run(app, host=HOST, port=port, log_level="warning")


def main() -> None:
    port = _free_port()
    url = f"http://{HOST}:{port}"

    server_thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    server_thread.start()

    # Give uvicorn a moment to come up.
    time.sleep(1.0)

    try:
        import webview  # pywebview

        api = JsApi()

        def _spawn():
            w = webview.create_window(
                "Diamond Scorer",
                url,
                width=1360,
                height=900,
                min_size=(1100, 720),
                background_color="#0b1220",
                js_api=api,
            )
            api.window = w
            return w

        # Launch the native window, trying renderers in order of preference.
        # A 32-bit build on an older PC (e.g. Windows 7/8) may not have the
        # modern WebView2 runtime installed, so we fall back to the built-in
        # MSHTML (Internet Explorer) engine that ships with Windows itself.
        # ``None`` lets pywebview auto-select the best available backend first.
        attempts = [None, "edgechromium", "mshtml"]
        last_err = None
        started = False
        for gui in attempts:
            # Clear any window left over from a failed attempt so we do not
            # accumulate duplicates on the fallback.
            try:
                getattr(webview, "windows", []).clear()
            except Exception:
                pass
            try:
                _spawn()
                if gui:
                    webview.start(gui=gui)
                else:
                    webview.start()
                started = True
                break
            except Exception as exc:  # pragma: no cover - runtime guard
                last_err = exc
                continue
        if not started and last_err is not None:
            raise last_err
    except Exception:  # pragma: no cover - headless fallback
        print(f"\nDiamond Scorer is running at: {url}")
        print("pywebview not available -- open the URL above in your browser.")
        print("Press Ctrl+C to stop.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
