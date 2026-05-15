"""Public landing page. Anonymous users land here on first contact."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from web.auth import get_current_user
from web.templates_setup import lang_for, templates

router = APIRouter()


@router.get("/")
async def landing(
    request: Request,
    user: Annotated[Optional[dict], Depends(get_current_user)] = None,
    lang: str | None = None,
):
    """Public marketing page. Authenticated users get redirected straight to /app."""
    if user is not None:
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(
        request,
        "landing.html",
        {"lang": lang or lang_for(None), "user": None},
    )
