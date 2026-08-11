"""Owner-only admin website: dashboard, prompt editor (versioned), config editor.

Mounted into the same FastAPI app as the bot (see app/main.py) so the whole
thing is one process/container.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.admin.auth import (
    SESSION_COOKIE_NAME,
    create_session_cookie,
    is_valid_session_cookie,
    verify_password,
)
from app.config import settings
from app.db import supabase_client as db

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _is_authed(request: Request) -> bool:
    return is_valid_session_cookie(request.cookies.get(SESSION_COOKIE_NAME))


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"authed": False})


@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if username != settings.admin_username or not verify_password(
        password, settings.admin_password_hash
    ):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"authed": False, "error": "Sai tên đăng nhập hoặc mật khẩu."},
            status_code=401,
        )
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_cookie(),
        httponly=True,
        samesite="lax",
        # Only require HTTPS for the cookie when actually served over HTTPS
        # (production, behind the reverse proxy) - a hardcoded True would
        # make the browser silently drop the cookie during local http:// testing.
        secure=request.url.scheme == "https",
        max_age=7 * 24 * 3600,
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("")
def dashboard(request: Request):
    if not _is_authed(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    holdings_count = len(db.list_holdings())
    watchlist_count = len(db.list_watchlist())
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "authed": True,
            "model": settings.claude_model,
            "market_data_source": settings.market_data_source,
            "holdings_count": holdings_count,
            "watchlist_count": watchlist_count,
        },
    )


@router.get("/prompts")
def prompts_form(request: Request):
    if not _is_authed(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    content = db.get_active_prompt("system") or ""
    versions = db.list_prompt_versions("system")
    return templates.TemplateResponse(
        request,
        "prompts.html",
        {"authed": True, "content": content, "versions": versions, "saved": False},
    )


@router.post("/prompts")
def prompts_submit(request: Request, content: str = Form(...)):
    if not _is_authed(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    saved = db.save_prompt_version("system", content)
    versions = db.list_prompt_versions("system")
    return templates.TemplateResponse(
        request,
        "prompts.html",
        {
            "authed": True,
            "content": content,
            "versions": versions,
            "saved": True,
            "current_version": saved["version"],
        },
    )


@router.get("/config")
def config_form(request: Request):
    if not _is_authed(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    interval = db.get_config("alert_check_interval_minutes", 5)
    return templates.TemplateResponse(
        request,
        "config.html",
        {"authed": True, "alert_check_interval_minutes": interval, "saved": False},
    )


@router.post("/config")
def config_submit(request: Request, alert_check_interval_minutes: int = Form(...)):
    if not _is_authed(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    db.set_config("alert_check_interval_minutes", alert_check_interval_minutes)
    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "authed": True,
            "alert_check_interval_minutes": alert_check_interval_minutes,
            "saved": True,
        },
    )
