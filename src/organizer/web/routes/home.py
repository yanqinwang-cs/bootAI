from __future__ import annotations

from fastapi import APIRouter
from urllib.parse import parse_qs
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from organizer.web.security import (
    LaunchTokenGate,
    csrf_token_for_session,
    initialize_authenticated_session,
    is_authenticated,
    validate_csrf_token,
    validate_same_origin,
)
from organizer.web.scan_jobs import ScanAlreadyRunning, ScanJobController

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
            context=_scan_context(request),
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.post("/scan", include_in_schema=False)
    async def start_scan(request: Request) -> Response:
        _require_authenticated(request)
        submitted_token = await _csrf_token_from_form(request)
        try:
            validate_same_origin(request)
            validate_csrf_token(request.session, submitted_token)
        except ValueError as error:
            raise HTTPException(status_code=403, detail="scan request unavailable") from error

        controller: ScanJobController = request.app.state.scan_jobs
        try:
            controller.start()
        except ScanAlreadyRunning as error:
            raise HTTPException(status_code=409, detail="scan already running") from error

        if request.headers.get("hx-request", "").lower() == "true":
            response = templates.TemplateResponse(
                request=request,
                name="scan_panel.html",
                context=_scan_context(request),
                status_code=202,
            )
            response.headers["Cache-Control"] = "no-store"
            return response
        return RedirectResponse(url="/", status_code=303)

    @router.get("/scan/status", include_in_schema=False)
    async def scan_status(request: Request) -> Response:
        _require_authenticated(request)
        response = templates.TemplateResponse(
            request=request,
            name="scan_panel.html",
            context=_scan_context(request),
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return router


def _require_authenticated(request: Request) -> None:
    if not is_authenticated(request.session):
        raise HTTPException(status_code=403, detail="session unavailable")


async def _csrf_token_from_form(request: Request) -> str | None:
    body = await request.body()
    values = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    tokens = values.get("csrf_token", [])
    return tokens[0] if len(tokens) == 1 else None


def _scan_context(request: Request) -> dict[str, object]:
    controller: ScanJobController = request.app.state.scan_jobs
    snapshot = controller.snapshot()
    relative_report_path = None
    if snapshot.report_path is not None:
        relative_report_path = snapshot.report_path.resolve().relative_to(
            request.app.state.web_config.root
        ).as_posix()
    return {
        "locked_root": request.app.state.web_config.root,
        "csrf_token": csrf_token_for_session(request.session),
        "scan": snapshot,
        "relative_report_path": relative_report_path,
    }


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
