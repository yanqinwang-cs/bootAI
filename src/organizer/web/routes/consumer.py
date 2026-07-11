from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from organizer.web.consumer_presenter import (
    ConsumerSurface,
    SURFACE_SPECS,
    build_consumer_page,
    build_plan_summary,
    card_for_selected,
    feedback_for_card,
)
from organizer.web.review_explorer import ReviewExplorerSnapshot
from organizer.web.security import csrf_token_for_session, is_authenticated


def create_consumer_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter()

    @router.get("/duplicates", include_in_schema=False)
    async def duplicates(request: Request) -> Response:
        return render_consumer_page(
            request,
            templates,
            ConsumerSurface.DUPLICATES,
        )

    @router.get("/organize", include_in_schema=False)
    async def organize(request: Request) -> Response:
        return render_consumer_page(
            request,
            templates,
            ConsumerSurface.ORGANIZE,
        )

    @router.get("/attention", include_in_schema=False)
    async def attention(request: Request) -> Response:
        return render_consumer_page(
            request,
            templates,
            ConsumerSurface.ATTENTION,
        )

    @router.get("/settings", include_in_schema=False)
    async def settings(request: Request) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        if request.query_params:
            return _consumer_error(
                request,
                templates,
                "The settings page options are invalid.",
                400,
            )
        response = templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "locked_root": request.app.state.web_config.root,
                "application_version": _application_version(),
            },
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return router


def render_consumer_page(
    request: Request,
    templates: Jinja2Templates,
    surface: ConsumerSurface,
    *,
    template_name: str = "consumer_review.html",
    page_override: int | None = None,
    selected_override: str | None = None,
    saved_override: bool = False,
) -> Response:
    if not is_authenticated(request.session):
        return _session_error(request, templates)
    try:
        query = _consumer_query(request) if page_override is None else {}
        page_number = page_override or int(query["page"])
        selected = selected_override or query.get("selected")
        saved_requested = saved_override or query.get("saved") == "1"
    except ValueError:
        return _consumer_error(
            request,
            templates,
            "The page options are invalid.",
            400,
        )

    explorer = _explorer_snapshot(request)
    context: dict[str, object] = {
        "explorer": explorer,
        "spec": SURFACE_SPECS[surface],
        "surface": surface.value,
        "locked_root": request.app.state.web_config.root,
    }
    if explorer.status == "completed" and explorer.session is not None:
        try:
            page = build_consumer_page(
                explorer.session,
                surface,
                page=page_number,
            )
            selected_card = card_for_selected(page, selected)
        except ValueError:
            return _consumer_error(
                request,
                templates,
                "That consumer review page is unavailable.",
                400,
            )
        plan_summary = build_plan_summary(explorer.session)
        saved_feedback = (
            saved_requested
            and not plan_summary.dirty
            and plan_summary.saved_plan_relative is not None
        )
        context.update(
            {
                "page": page,
                "plan_summary": plan_summary,
                "selected_card": selected_card,
                "decision_feedback": (
                    feedback_for_card(selected_card)
                    if selected_card is not None
                    else None
                ),
                "saved_feedback": saved_feedback,
                "csrf_token": csrf_token_for_session(request.session),
                "summary_surface": surface.value,
                "summary_page": page.page,
            }
        )

    response = templates.TemplateResponse(
        request=request,
        name=template_name,
        context=context,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _consumer_query(request: Request) -> dict[str, str]:
    allowed = {"page", "selected", "saved"}
    if set(request.query_params) - allowed:
        raise ValueError("unsupported consumer query")
    query = {"page": "1"}
    for name in allowed:
        values = request.query_params.getlist(name)
        if len(values) > 1:
            raise ValueError("duplicate consumer query")
        if values:
            query[name] = values[0]
    if query.get("saved") not in {None, "1"}:
        raise ValueError("invalid save feedback")
    if int(query["page"]) < 1:
        raise ValueError("invalid consumer page")
    return query


def _explorer_snapshot(request: Request) -> ReviewExplorerSnapshot:
    return request.app.state.review_explorer.snapshot(
        request.app.state.scan_jobs.snapshot()
    )


def _application_version() -> str:
    try:
        return version("bootai")
    except PackageNotFoundError:
        return "Development build"


def _consumer_error(
    request: Request,
    templates: Jinja2Templates,
    message: str,
    status_code: int,
) -> Response:
    response = templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "page_title": "Page unavailable",
            "heading": "Page unavailable",
            "message": message,
        },
        status_code=status_code,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _session_error(request: Request, templates: Jinja2Templates) -> Response:
    return _consumer_error(
        request,
        templates,
        "This bootAI session is not available. "
        "Launch bootAI again from the local application.",
        403,
    )
