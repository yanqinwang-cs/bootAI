from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.templating import Jinja2Templates

from organizer.application.review_service import (
    find_review_conflicts,
    get_review_item,
    get_review_item_metadata,
    get_review_view,
    review_category_counts,
    summarize_review_session,
    update_review_filter,
    update_review_page,
    update_review_page_size,
    update_review_sort,
)
from organizer.application.view_models import ReviewApplicationSession
from organizer.web.forms import FormDataError, read_urlencoded_form
from organizer.web.review_explorer import (
    ReviewConfirmationRejected,
    ReviewExplorerSnapshot,
    ReviewExplorerStore,
    ReviewItemNotFound,
    ReviewPreviewUnavailable,
    ReviewSessionUnavailable,
)
from organizer.web.security import (
    csrf_token_for_session,
    is_authenticated,
    session_id_for_session,
    validate_csrf_token,
    validate_same_origin,
)

_CATEGORY_LABELS = {
    "all": "All findings",
    "duplicate": "Exact duplicates",
    "organization": "Organization suggestions",
    "review_candidate": "Needs review",
}
_DECISION_LABELS = {
    "approved": "Organize",
    "rejected": "Keep here",
    "undecided": "Review later",
}
_BULK_ACTION_LABELS = {
    "approved": "Organize current page",
    "rejected": "Keep current page here",
    "undecided": "Mark current page for later review",
}
_VIEW_DEFAULTS = {
    "category": "all",
    "decision": "",
    "review_category": "",
    "sort": "id",
    "direction": "asc",
    "page": "1",
    "page_size": "25",
}


class ReviewRequestError(ValueError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def create_review_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter()

    @router.get("/review", name="review", include_in_schema=False)
    async def review(request: Request) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        try:
            query = _view_query(request)
            return _render_review(request, templates, query)
        except ValueError:
            return _review_error(
                request,
                templates,
                "The review view parameters are invalid.",
                400,
            )

    @router.post(
        "/review/items/{item_id}/decision",
        name="review_item_decision",
        include_in_schema=False,
    )
    async def review_item_decision(
        request: Request,
        item_id: str,
    ) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        try:
            form = await _validated_mutation_form(
                request,
                allowed_fields={"csrf_token", "decision"},
            )
            query = _view_query(request)
            decision = form.get("decision", "")
            if decision not in _DECISION_LABELS:
                raise ReviewRequestError(
                    "That review decision is not supported.",
                    400,
                )
            store = _review_store(request)
            change = store.change_decision(
                _scan_snapshot(request),
                item_id,
                decision,
                project=lambda session: _view_session(session, query),
            )
            updated_query = _clamped_query(change.session, query)
        except ReviewItemNotFound:
            return _review_error(
                request,
                templates,
                "That review row was not found.",
                404,
            )
        except ReviewSessionUnavailable:
            return _review_error(
                request,
                templates,
                "No completed scan review session is available.",
                409,
            )
        except ReviewRequestError as error:
            return _review_error(
                request,
                templates,
                str(error),
                error.status_code,
            )
        except ValueError:
            return _review_error(
                request,
                templates,
                "The review view parameters are invalid.",
                400,
            )

        review_url = _review_url(updated_query)
        if request.headers.get("hx-request", "").lower() == "true":
            response = _render_review(
                request,
                templates,
                updated_query,
                template_name="review_workspace.html",
            )
            response.headers["HX-Replace-Url"] = review_url
            return response
        return RedirectResponse(review_url, status_code=303)

    @router.post(
        "/review/page-decision/preview",
        name="review_page_decision_preview",
        include_in_schema=False,
    )
    async def review_page_decision_preview(request: Request) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        try:
            form = await _validated_mutation_form(
                request,
                allowed_fields={"csrf_token", "decision"},
            )
            query = _view_query(request)
            decision = form.get("decision", "")
            if decision not in _DECISION_LABELS:
                raise ReviewRequestError(
                    "That current-page decision is not supported.",
                    400,
                )
            result = _review_store(request).preview_page_decision(
                _scan_snapshot(request),
                session_id_for_session(request.session),
                decision,
                project=lambda session: _view_session(session, query),
                view_query=tuple(sorted(query.items())),
            )
        except ReviewSessionUnavailable:
            return _review_error(
                request,
                templates,
                "No completed scan review session is available.",
                409,
            )
        except ReviewRequestError as error:
            return _review_error(
                request,
                templates,
                str(error),
                error.status_code,
            )
        except ValueError:
            return _review_error(
                request,
                templates,
                "The review view parameters are invalid.",
                400,
            )

        response = templates.TemplateResponse(
            request=request,
            name="review_page_decision.html",
            context={
                "preview": result.preview,
                "preview_token": result.preview_token,
                "action_label": _BULK_ACTION_LABELS[decision],
                "decision_labels": _DECISION_LABELS,
                "category_labels": _CATEGORY_LABELS,
                "csrf_token": csrf_token_for_session(request.session),
                "review_url": _review_url(query),
            },
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.post(
        "/review/page-decision/confirm",
        name="review_page_decision_confirm",
        include_in_schema=False,
    )
    async def review_page_decision_confirm(request: Request) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        try:
            form = await _validated_mutation_form(
                request,
                allowed_fields={
                    "csrf_token",
                    "preview_token",
                    "confirmation",
                },
            )
            result = _review_store(request).confirm_page_decision(
                _scan_snapshot(request),
                session_id_for_session(request.session),
                form.get("preview_token", ""),
                form.get("confirmation", ""),
            )
            query = _clamped_query(
                result.change.session,
                dict(result.view_query),
            )
        except ReviewConfirmationRejected as error:
            return _review_error(request, templates, str(error), 400)
        except ReviewPreviewUnavailable as error:
            return _review_error(request, templates, str(error), 400)
        except ReviewSessionUnavailable:
            return _review_error(
                request,
                templates,
                "No completed scan review session is available.",
                409,
            )
        except ReviewRequestError as error:
            return _review_error(
                request,
                templates,
                str(error),
                error.status_code,
            )
        return RedirectResponse(_review_url(query), status_code=303)

    @router.post("/review/save", name="review_save", include_in_schema=False)
    async def review_save(request: Request) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        try:
            await _validated_mutation_form(
                request,
                allowed_fields={"csrf_token"},
            )
            query = _view_query(request)
            result = _review_store(request).save(
                _scan_snapshot(request),
                project=lambda session: _view_session(session, query),
            )
            updated_query = _clamped_query(result.session, query)
        except ReviewSessionUnavailable:
            return _review_error(
                request,
                templates,
                "No completed scan review session is available.",
                409,
            )
        except ReviewRequestError as error:
            return _review_error(
                request,
                templates,
                str(error),
                error.status_code,
            )
        except (OSError, UnicodeError, ValueError):
            return _review_error(
                request,
                templates,
                "The reviewed plan could not be saved. "
                "Your unsaved review changes are still available.",
                500,
            )
        return RedirectResponse(_review_url(updated_query), status_code=303)

    @router.get(
        "/review/items/{item_id}",
        name="review_item",
        include_in_schema=False,
    )
    async def review_item(request: Request, item_id: str) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        explorer = _explorer_snapshot(request)
        if explorer.status != "completed" or explorer.session is None:
            return _review_error(
                request,
                templates,
                "No completed scan is available.",
                404,
            )
        try:
            item = get_review_item(explorer.session, item_id)
        except ValueError:
            return _review_error(
                request,
                templates,
                "That review row was not found.",
                404,
            )

        metadata = get_review_item_metadata(explorer.session, item.id)
        modified_time = (
            datetime.fromtimestamp(metadata.modified_time).astimezone()
            if metadata.modified_time is not None
            else None
        )
        response = templates.TemplateResponse(
            request=request,
            name="review_item.html",
            context={
                "locked_root": request.app.state.web_config.root,
                "item": item,
                "decision_label": _DECISION_LABELS.get(
                    item.decision,
                    item.decision,
                ),
                "source_relative": _relative_path(
                    item.plan_item.source,
                    explorer.session.root,
                ),
                "destination_relative": _relative_path(
                    item.plan_item.destination,
                    explorer.session.root,
                ),
                "size_bytes": metadata.size_bytes,
                "modified_time": modified_time,
            },
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.get(
        "/review/conflicts",
        name="review_conflicts",
        include_in_schema=False,
    )
    async def review_conflicts(request: Request) -> Response:
        if not is_authenticated(request.session):
            return _session_error(request, templates)
        explorer = _explorer_snapshot(request)
        if explorer.status != "completed" or explorer.session is None:
            return _render_state(request, templates, explorer)
        response = templates.TemplateResponse(
            request=request,
            name="review_conflicts.html",
            context={
                "conflicts": find_review_conflicts(explorer.session),
                "locked_root": request.app.state.web_config.root,
            },
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return router


async def _validated_mutation_form(
    request: Request,
    *,
    allowed_fields: set[str],
) -> dict[str, str]:
    try:
        form = await read_urlencoded_form(
            request,
            allowed_fields=allowed_fields,
        )
    except FormDataError as error:
        raise ReviewRequestError(
            "The review form submission is invalid.",
            400,
        ) from error
    try:
        validate_same_origin(request)
        validate_csrf_token(request.session, form.get("csrf_token"))
    except ValueError as error:
        raise ReviewRequestError(
            "The review request could not be authenticated.",
            403,
        ) from error
    return form


def _view_query(request: Request) -> dict[str, str]:
    unexpected = set(request.query_params) - set(_VIEW_DEFAULTS)
    if unexpected:
        raise ValueError("unsupported review query parameter")
    query = dict(_VIEW_DEFAULTS)
    for name in _VIEW_DEFAULTS:
        values = request.query_params.getlist(name)
        if len(values) > 1:
            raise ValueError("duplicate review query parameter")
        if values:
            query[name] = values[0]
    return query


def _view_session(
    session: ReviewApplicationSession,
    query: dict[str, str],
) -> ReviewApplicationSession:
    category = query["category"]
    if category not in _CATEGORY_LABELS:
        raise ValueError("invalid category")
    if category != "all":
        session = update_review_filter(session, "category", category)
    if query["decision"]:
        session = update_review_filter(
            session,
            "decision",
            query["decision"],
        )
    if query["review_category"]:
        session = update_review_filter(
            session,
            "review_category",
            query["review_category"],
        )
    session = update_review_sort(
        session,
        query["sort"],
        query["direction"],
    )
    session = update_review_page_size(session, query["page_size"])
    try:
        requested_page = int(query["page"])
    except ValueError as error:
        raise ValueError("invalid page") from error
    if requested_page < 1:
        raise ValueError("invalid page")
    view = get_review_view(session)
    if view.total_pages == 0:
        if requested_page != 1:
            raise ValueError("invalid page")
    elif requested_page != 1:
        session = update_review_page(session, str(requested_page))
    return session


def _clamped_query(
    session: ReviewApplicationSession,
    query: dict[str, str],
) -> dict[str, str]:
    first_page_query = {**query, "page": "1"}
    projected = _view_session(session, first_page_query)
    view = get_review_view(projected)
    try:
        requested_page = max(1, int(query["page"]))
    except ValueError:
        requested_page = 1
    page = min(requested_page, view.total_pages) if view.total_pages else 1
    return {**query, "page": str(page)}


def _render_review(
    request: Request,
    templates: Jinja2Templates,
    query: dict[str, str],
    *,
    template_name: str = "review.html",
) -> Response:
    explorer = _explorer_snapshot(request)
    if explorer.status != "completed" or explorer.session is None:
        return _render_state(request, templates, explorer)
    session = _view_session(explorer.session, query)
    view = get_review_view(session)
    summary = summarize_review_session(session)
    conflicts = find_review_conflicts(session)
    response = templates.TemplateResponse(
        request=request,
        name=template_name,
        context=_review_context(
            request,
            explorer,
            session,
            view,
            summary,
            conflicts,
            query,
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _review_context(
    request: Request,
    explorer: ReviewExplorerSnapshot,
    session: ReviewApplicationSession,
    view,
    summary: dict[str, int],
    conflicts,
    query: dict[str, str],
) -> dict[str, object]:
    base_session = explorer.session
    assert base_session is not None
    query_string = urlencode(query)
    category_urls = {
        category: _review_url({**query, "category": category, "page": "1"})
        for category in _CATEGORY_LABELS
    }
    previous_url = (
        _review_url({**query, "page": str(view.page - 1)})
        if view.page > 1
        else None
    )
    next_url = (
        _review_url({**query, "page": str(view.page + 1)})
        if view.page < view.total_pages
        else None
    )
    saved_plan_relative = None
    if base_session.saved_plan_path is not None:
        try:
            saved_plan_relative = base_session.saved_plan_path.resolve().relative_to(
                base_session.root
            ).as_posix()
        except ValueError:
            saved_plan_relative = None
    return {
        "locked_root": request.app.state.web_config.root,
        "explorer": explorer,
        "session": session,
        "base_session": base_session,
        "view": view,
        "summary": summary,
        "category_counts": review_category_counts(session),
        "category_labels": _CATEGORY_LABELS,
        "decision_labels": _DECISION_LABELS,
        "bulk_action_labels": _BULK_ACTION_LABELS,
        "active_category": query["category"],
        "active_filters": dict(session.view_state.filters),
        "conflicts": conflicts,
        "warning_count": len(explorer.warnings),
        "row_metadata": {
            row.id: get_review_item_metadata(session, row.id)
            for row in view.rows
        },
        "csrf_token": csrf_token_for_session(request.session),
        "view_query_string": query_string,
        "review_url": _review_url(query),
        "category_urls": category_urls,
        "previous_url": previous_url,
        "next_url": next_url,
        "saved_plan_relative": saved_plan_relative,
    }


def _review_url(query: dict[str, str]) -> str:
    return f"/review?{urlencode(query)}"


def _review_store(request: Request) -> ReviewExplorerStore:
    return request.app.state.review_explorer


def _scan_snapshot(request: Request):
    return request.app.state.scan_jobs.snapshot()


def _explorer_snapshot(request: Request) -> ReviewExplorerSnapshot:
    return _review_store(request).snapshot(_scan_snapshot(request))


def _render_state(
    request: Request,
    templates: Jinja2Templates,
    explorer: ReviewExplorerSnapshot,
) -> Response:
    response = templates.TemplateResponse(
        request=request,
        name="review_state.html",
        context={
            "locked_root": request.app.state.web_config.root,
            "explorer": explorer,
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _review_error(
    request: Request,
    templates: Jinja2Templates,
    message: str,
    status_code: int,
) -> Response:
    response = templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "page_title": "Review unavailable",
            "heading": "Review unavailable",
            "message": message,
        },
        status_code=status_code,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _session_error(request: Request, templates: Jinja2Templates) -> Response:
    return _review_error(
        request,
        templates,
        "This bootAI session is not available. "
        "Launch bootAI again from the local application.",
        403,
    )


def _relative_path(path, root) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
