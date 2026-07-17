"""FastAPI entry point for the Finance web app.

Server-rendered Jinja2 + Tailwind + HTMX stack. Mobile-first.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils import db  # noqa: E402
from web.auth import CSRFMiddleware  # noqa: E402
from web.routes import admin as admin_routes  # noqa: E402
from web.routes import app_view as app_view_routes  # noqa: E402
from web.routes import auth as auth_routes  # noqa: E402
from web.routes import dashboard as dashboard_routes  # noqa: E402
from web.routes import landing as landing_routes  # noqa: E402
from web.routes import recurring as recurring_routes  # noqa: E402
from web.routes import settings as settings_routes  # noqa: E402
from web.scheduler import _scheduler_loop  # noqa: E402
from web.templates_setup import templates  # noqa: E402

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Boot/shut the recurring-transaction scheduler with the app.

    Pre-v2.x this lived in the bot process; since the web is the
    canonical surface now, the scheduler runs here so single-service
    deployments (just `docker compose up -d web`) still execute
    recurring rules. Tests can disable it by setting
    ``WEB_SCHEDULER_DISABLED=1`` in the environment.
    """
    stop_event: asyncio.Event | None = None
    task: asyncio.Task | None = None
    if os.getenv("WEB_SCHEDULER_DISABLED") != "1":
        stop_event = asyncio.Event()
        task = asyncio.create_task(_scheduler_loop(stop_event))
    try:
        yield
    finally:
        if stop_event is not None:
            stop_event.set()
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (TimeoutError, asyncio.TimeoutError):
                log.warning("scheduler did not stop within 5s; cancelling")
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass


app = FastAPI(title="Finance", docs_url=None, redoc_url=None, lifespan=lifespan)

app.add_middleware(CSRFMiddleware)

db.setup_database()

app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

app.include_router(landing_routes.router)
app.include_router(auth_routes.router)
app.include_router(app_view_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(recurring_routes.router)
app.include_router(admin_routes.router)
app.include_router(settings_routes.router)


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    headers = exc.headers or {}
    # 303 + Location: actual browser redirect (used by require_user)
    if exc.status_code == 303 and "Location" in headers:
        return RedirectResponse(headers["Location"], status_code=303)
    # HTMX 401: empty body + HX-Redirect header so the browser follows
    if exc.status_code == 401 and "HX-Redirect" in headers:
        return HTMLResponse("", status_code=401, headers=headers)
    # 404: themed template
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request, "404.html", {"lang": "pt"}, status_code=404
        )
    # Default: pass through detail as plain text with the original status
    return PlainTextResponse(
        str(exc.detail), status_code=exc.status_code, headers=headers,
    )


def main() -> None:
    """Local dev entry: `python -m web.main`."""
    import uvicorn
    port = int(os.getenv("WEB_PORT", "8000"))
    uvicorn.run("web.main:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    main()
