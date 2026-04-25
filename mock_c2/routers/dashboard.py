from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates


router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=307)


@router.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {})
