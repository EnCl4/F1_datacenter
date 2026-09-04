"""T059 -- the local read-only API.

There are no write routes, and that is a design property rather than an omission: the
write path belongs exclusively to ingest, which keeps the derived store single-writer
(plan, Constitution Check VII). Starring a session is therefore a CLI action.

Bound to loopback. No authentication, because the service is local and single-user.
"""

from __future__ import annotations

import mimetypes
import webbrowser
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from f1dc.api.routes import sessions as sessions_routes
from f1dc.config import Paths

FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"

# Windows-specific, and it silently breaks the whole UI if missed.
#
# Python's mimetypes module seeds itself from the Windows registry, where .js is commonly
# registered as text/plain. Browsers enforce strict MIME checking on ES modules, so the
# bundle is refused and the page renders blank with only a console error to show for it.
# Registering the correct types explicitly makes the served frontend independent of
# whatever the local registry happens to say.
#
# init() must run FIRST: it is otherwise called lazily on the first lookup and re-reads
# the registry, discarding anything added beforehand.
mimetypes.init()
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def create_app(paths: Paths) -> FastAPI:
    app = FastAPI(
        title="F1 Data Center",
        description="Read-only access to captured F1 23 sessions.",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.paths = paths

    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    app.include_router(sessions_routes.router, prefix="/api")

    if FRONTEND_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        async def _index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

        @app.get("/{path:path}", include_in_schema=False)
        async def _spa(path: str) -> FileResponse:
            """Single-page app: unknown paths fall through to the shell."""
            candidate = FRONTEND_DIR / path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIR / "index.html")

    return app


def serve(paths: Paths, *, host: str = "127.0.0.1", port: int = 8420, open_browser: bool = False) -> int:
    import uvicorn

    if not FRONTEND_DIR.is_dir():
        print(
            f"note: no built frontend at {FRONTEND_DIR}; the API is still available at "
            f"http://{host}:{port}/api/docs"
        )
    url = f"http://{host}:{port}/"
    print(f"serving {url}  (data: {paths.data_dir})")
    if open_browser:
        webbrowser.open(url)

    uvicorn.run(create_app(paths), host=host, port=port, log_level="warning")
    return 0
