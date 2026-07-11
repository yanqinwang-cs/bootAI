from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.templating import Jinja2Templates

from organizer.web.consumer_presenter import (
    ConsumerSurface,
    SURFACE_SPECS,
    build_guided_module_page,
    feedback_for_card,
    module_for_surface,
    surface_url,
)
from organizer.web.forms import FormDataError, read_urlencoded_form
from organizer.web.review_explorer import (
    ReviewExplorerSnapshot,
    ReviewSessionUnavailable,
)
from organizer.web.security import (
    csrf_token_for_session,
    is_authenticated,
    validate_csrf_token,
    validate_same_origin,
)


class ModuleRequestError(ValueError):
    def __init__(self, status_code: int) -> None:
        super().__init__("module request unavailable")
        self.status_code = status_code


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

    for route, surface in (
        ("/duplicates/save", ConsumerSurface.DUPLICATES),
        ("/organize/save", ConsumerSurface.ORGANIZE),
        ("/attention/save", ConsumerSurface.ATTENTION),
    ):
        router.add_api_route(
            route,
            _module_save_handler(templates, surface),
            methods=["POST"],
            include_in_schema=False,
        )

    for route, surface in (
        ("/duplicates/revisit-skipped", ConsumerSurface.DUPLICATES),
        ("/organize/revisit-skipped", ConsumerSurface.ORGANIZE),
        ("/attention/revisit-skipped", ConsumerSurface.ATTENTION),
    ):
        router.add_api_route(
            route,
            _revisit_handler(templates, surface),
            methods=["POST"],
            include_in_schema=False,
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
    revisited_override: bool = False,
    save_summary_override=None,
) -> Response:
    if not is_authenticated(request.session):
        return _session_error(request, templates)
    try:
        query = _consumer_query(request) if page_override is None else {}
        page_number = page_override or int(query["page"])
        if page_number != 1:
            raise ValueError("guided modules do not paginate")
        selected = selected_override or query.get("selected")
        saved_requested = saved_override or query.get("saved") == "1"
        revisited_requested = (
            revisited_override or query.get("revisited") == "1"
        )
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
            module = module_for_surface(surface)
            page = build_guided_module_page(
                explorer.session,
                surface,
                explorer.queue_for(module),
                selected=selected,
            )
        except ValueError:
            return _consumer_error(
                request,
                templates,
                "That consumer review page is unavailable.",
                400,
            )
        context.update(
            {
                "page": page,
                "decision_feedback": (
                    feedback_for_card(page.selected_card)
                    if page.selected_card is not None
                    else None
                ),
                "saved_feedback": saved_requested,
                "revisited_feedback": revisited_requested,
                "save_summary": save_summary_override,
                "csrf_token": csrf_token_for_session(request.session),
                "save_action": {
                    ConsumerSurface.DUPLICATES: "/duplicates/save",
                    ConsumerSurface.ORGANIZE: "/organize/save",
                    ConsumerSurface.ATTENTION: "/attention/save",
                }[surface],
                "revisit_action": {
                    ConsumerSurface.DUPLICATES: "/duplicates/revisit-skipped",
                    ConsumerSurface.ORGANIZE: "/organize/revisit-skipped",
                    ConsumerSurface.ATTENTION: "/attention/revisit-skipped",
                }[surface],
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
    allowed = {"page", "selected", "saved", "revisited"}
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
    if query.get("revisited") not in {None, "1"}:
        raise ValueError("invalid revisit feedback")
    if int(query["page"]) < 1:
        raise ValueError("invalid consumer page")
    return query


def _module_save_handler(templates, surface):
    async def handler(request: Request) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        try:
            await _validated_form(request)
            module = module_for_surface(surface)
            result = request.app.state.review_explorer.save_module(
                request.app.state.scan_jobs.snapshot(),
                module,
                project=lambda session: session,
            )
        except ModuleRequestError as error:
            return _consumer_error(
                request,
                templates,
                "The save request is invalid. No choices were saved.",
                error.status_code,
            )
        except ReviewSessionUnavailable:
            return _consumer_error(
                request, templates, "No completed scan is available.", 409
            )
        except ValueError:
            return _consumer_error(
                request,
                templates,
                "This module has no savable findings. No artifact was written.",
                409,
            )
        except (OSError, UnicodeError):
            return _consumer_error(
                request,
                templates,
                "These choices could not be saved. Unsaved choices remain available.",
                500,
            )
        url = surface_url(surface, saved=True)
        if request.headers.get("hx-request", "").lower() == "true":
            response = render_consumer_page(
                request,
                templates,
                surface,
                template_name="consumer_workspace.html",
                page_override=1,
                saved_override=True,
                save_summary_override=result.summary,
            )
            response.headers["HX-Replace-Url"] = url
            return response
        return RedirectResponse(url, status_code=303)

    return handler


def _revisit_handler(templates, surface):
    async def handler(request: Request) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        try:
            await _validated_form(request)
            request.app.state.review_explorer.revisit_skipped(
                request.app.state.scan_jobs.snapshot(),
                module_for_surface(surface),
            )
        except ModuleRequestError as error:
            return _consumer_error(
                request,
                templates,
                "The queue request is invalid. No choices were changed.",
                error.status_code,
            )
        except ReviewSessionUnavailable:
            return _consumer_error(
                request, templates, "No completed scan is available.", 409
            )
        url = f"{surface_url(surface)}?revisited=1"
        if request.headers.get("hx-request", "").lower() == "true":
            response = render_consumer_page(
                request,
                templates,
                surface,
                template_name="consumer_workspace.html",
                page_override=1,
                revisited_override=True,
            )
            response.headers["HX-Replace-Url"] = url
            return response
        return RedirectResponse(url, status_code=303)

    return handler


async def _validated_form(request: Request) -> None:
    try:
        form = await read_urlencoded_form(
            request,
            allowed_fields={"csrf_token"},
        )
    except FormDataError as error:
        raise ModuleRequestError(400) from error
    try:
        validate_same_origin(request)
        validate_csrf_token(request.session, form.get("csrf_token"))
    except ValueError as error:
        raise ModuleRequestError(403) from error


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
