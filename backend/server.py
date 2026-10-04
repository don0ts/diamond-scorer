"""FastAPI application factory: mounts the API and serves the frontend SPA."""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .db import init_db

_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def _install_optional_basic_auth(app: FastAPI) -> None:
    """Enable HTTP Basic auth for the whole app when ``DIAMONDSCORER_AUTH`` is set.

    The variable format is ``user:password``. This is OFF by default so local /
    desktop use is unchanged; set it when hosting Diamond Scorer on a public
    website so the data is not world-writable. ``/health`` stays open so load
    balancers can probe it.
    """
    cred = os.environ.get("DIAMONDSCORER_AUTH", "").strip()
    if not cred or ":" not in cred:
        return
    want_user, want_pass = cred.split(":", 1)

    @app.middleware("http")
    async def _basic_auth(request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        header = request.headers.get("authorization", "")
        ok = False
        if header.lower().startswith("basic "):
            try:
                raw = base64.b64decode(header[6:]).decode("utf-8", "replace")
                user, _, pw = raw.partition(":")
                # Constant-time comparison to avoid leaking length/content.
                ok = (secrets.compare_digest(user, want_user)
                      and secrets.compare_digest(pw, want_pass))
            except Exception:
                ok = False
        if not ok:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Diamond Scorer"'},
                content="Authentication required.",
            )
        return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(title="Diamond Scorer", version="0.1.0")

    # Initialise the schema eagerly so the DB is ready regardless of how the
    # app is launched (uvicorn, TestClient, or PyInstaller bundle).
    init_db()

    # Optional auth for hosted/public deployments (no-op unless env var set).
    _install_optional_basic_auth(app)

    app.include_router(api_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Serve static assets (css/js) and index.html for the SPA.
    app.mount("/css", StaticFiles(directory=str(_FRONTEND / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(_FRONTEND / "js")), name="js")

    @app.get("/")
    def index():
        return FileResponse(str(_FRONTEND / "index.html"))

    return app


app = create_app()
