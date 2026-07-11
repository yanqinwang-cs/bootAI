from __future__ import annotations

from fastapi import APIRouter
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
from organizer.web.forms import FormDataError, read_urlencoded_form
from organizer.web.consumer_presenter import (
    ConsumerSurface,
    build_home_module_statuses,
    build_plan_summary,
    consumer_card_counts,
    parse_surface,
    surface_url,
)
from organizer.web.formatting import folder_name, format_bytes, format_local_time
from organizer.web.review_explorer import (
    ReviewExplorerStore,
    UnsavedReviewChanges,
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
        try:
            saved_requested = _home_saved_requested(request)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="home request unavailable") from error
        context = _scan_context(request)
        plan_summary = context.get("plan_summary")
        context["saved_feedback"] = bool(
            saved_requested
            and plan_summary is not None
            and not plan_summary.dirty
            and plan_summary.saved_plan_relative is not None
        )
        response = templates.TemplateResponse(
            request=request,
            name="home.html",
            context=context,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.get("/scans", include_in_schema=False)
    async def scans(request: Request) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        if request.query_params:
            raise HTTPException(status_code=400, detail="scans request unavailable")
        response = templates.TemplateResponse(
            request=request,
            name="scans.html",
            context=_scan_context(request, surface=ConsumerSurface.SCANS),
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.post("/scan", include_in_schema=False)
    async def start_scan(request: Request) -> Response:
        _require_authenticated(request)
        try:
            surface = _scan_surface(request)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="scan request unavailable") from error
        try:
            form = await read_urlencoded_form(
                request,
                allowed_fields={"csrf_token"},
            )
        except FormDataError as error:
            raise HTTPException(status_code=400, detail="scan request unavailable") from error
        try:
            validate_same_origin(request)
            validate_csrf_token(request.session, form.get("csrf_token"))
        except ValueError as error:
            raise HTTPException(status_code=403, detail="scan request unavailable") from error

        controller: ScanJobController = request.app.state.scan_jobs
        explorer: ReviewExplorerStore = request.app.state.review_explorer
        try:
            explorer.start_scan(controller)
        except UnsavedReviewChanges as error:
            blocked_modules = tuple(
                {
                    "duplicates": "Duplicate copies",
                    "organization": "Files to organize",
                    "attention": "Needs attention",
                }[module.value]
                for module in error.modules
            )
            if request.headers.get("hx-request", "").lower() == "true":
                response = templates.TemplateResponse(
                    request=request,
                    name="scan_panel.html",
                    context={
                        **_scan_context(request, surface=surface),
                        "scan_blocked_message": (
                            "Save these choices before scanning again. "
                            "bootAI did not discard them."
                        ),
                        "scan_blocked_modules": blocked_modules,
                    },
                    status_code=409,
                )
            else:
                response = templates.TemplateResponse(
                    request=request,
                    name="scan_blocked.html",
                    context={
                        "page_title": "Unsaved review changes",
                        "heading": "Unsaved review changes",
                        "scan_blocked_modules": blocked_modules,
                    },
                    status_code=409,
                )
            response.headers["Cache-Control"] = "no-store"
            return response
        except ScanAlreadyRunning as error:
            raise HTTPException(status_code=409, detail="scan already running") from error

        if request.headers.get("hx-request", "").lower() == "true":
            response = templates.TemplateResponse(
                request=request,
                name="scan_panel.html",
                context=_scan_context(request, surface=surface),
                status_code=202,
            )
            response.headers["Cache-Control"] = "no-store"
            return response
        return RedirectResponse(url=surface_url(surface), status_code=303)

    @router.get("/scan/status", include_in_schema=False)
    async def scan_status(request: Request) -> Response:
        _require_authenticated(request)
        try:
            surface = _scan_surface(request)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="scan request unavailable") from error
        response = templates.TemplateResponse(
            request=request,
            name="scan_panel.html",
            context=_scan_context(request, surface=surface),
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return router


def _require_authenticated(request: Request) -> None:
    if not is_authenticated(request.session):
        raise HTTPException(status_code=403, detail="session unavailable")


def _scan_context(
    request: Request,
    *,
    surface: ConsumerSurface = ConsumerSurface.HOME,
) -> dict[str, object]:
    controller: ScanJobController = request.app.state.scan_jobs
    snapshot = controller.snapshot()
    relative_report_path = None
    if snapshot.report_path is not None:
        relative_report_path = snapshot.report_path.resolve().relative_to(
            request.app.state.web_config.root
        ).as_posix()
    explorer = request.app.state.review_explorer.snapshot(snapshot)
    plan_summary = None
    card_counts = None
    module_statuses = None
    if explorer.status == "completed" and explorer.session is not None:
        plan_summary = build_plan_summary(explorer.session)
        card_counts = consumer_card_counts(explorer.session)
        module_statuses = build_home_module_statuses(
            explorer.session,
            explorer.module_queues,
        )
    return {
        "locked_root": request.app.state.web_config.root,
        "selected_folder": folder_name(request.app.state.web_config.root),
        "csrf_token": csrf_token_for_session(request.session),
        "scan": snapshot,
        "scan_surface": surface.value,
        "scan_action": f"/scan?surface={surface.value}",
        "scan_status_url": f"/scan/status?surface={surface.value}",
        "last_scan_time": format_local_time(snapshot.completed_at),
        "total_size": (
            format_bytes(snapshot.result.summary.total_bytes)
            if snapshot.result is not None
            else "Not available"
        ),
        "duplicate_space": (
            format_bytes(snapshot.result.summary.potential_duplicate_bytes)
            if snapshot.result is not None
            else "0 B"
        ),
        "relative_report_path": relative_report_path,
        "explorer": explorer,
        "plan_summary": plan_summary,
        "card_counts": card_counts,
        "module_statuses": module_statuses,
        "summary_surface": ConsumerSurface.HOME.value,
        "summary_page": None,
    }


def _scan_surface(request: Request) -> ConsumerSurface:
    unexpected = set(request.query_params) - {"surface"}
    if unexpected:
        raise ValueError("unsupported scan query")
    values = request.query_params.getlist("surface")
    if len(values) > 1:
        raise ValueError("duplicate scan surface")
    return parse_surface(
        values[0] if values else None,
        allowed={ConsumerSurface.HOME, ConsumerSurface.SCANS},
        default=ConsumerSurface.HOME,
    )


def _home_saved_requested(request: Request) -> bool:
    if set(request.query_params) - {"saved"}:
        raise ValueError("unsupported home query")
    values = request.query_params.getlist("saved")
    if len(values) > 1 or (values and values[0] != "1"):
        raise ValueError("invalid home save feedback")
    return bool(values)


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
