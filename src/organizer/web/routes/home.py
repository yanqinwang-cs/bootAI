from __future__ import annotations

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from organizer.web.security import (
    LaunchTokenGate,
    initialize_authenticated_session,
    is_authenticated,
)

_SESSION_UNAVAILABLE = (
    "This bootAI session is not available. "
    "Launch bootAI again from the local application."
)


def create_home_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz", include_in_schema=False)
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @router.get("/launch/{token}", include_in_schema=False)
    async def launch(request: Request, token: str) -> Response:
        gate: LaunchTokenGate = request.app.state.launch_token_gate
        if not gate.consume(token):
            return _session_error(request, templates)
        initialize_authenticated_session(request.session)
        return RedirectResponse(
            url="/",
            status_code=303,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/", include_in_schema=False)
    async def home(request: Request) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        response = templates.TemplateResponse(
            request=request,
            name="home.html",
            context={"locked_root": request.app.state.web_config.root},
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return router


def _session_error(
    request: Request,
    templates: Jinja2Templates,
) -> Response:
    response = templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "page_title": "Session unavailable",
            "heading": "Session unavailable",
            "message": _SESSION_UNAVAILABLE,
        },
        status_code=403,
    )
    response.headers["Cache-Control"] = "no-store"
    return response
