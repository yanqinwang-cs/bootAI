from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response
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
from organizer.web.review_explorer import ReviewExplorerSnapshot, ReviewExplorerStore


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


def create_review_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter()

    @router.get("/review", name="review", include_in_schema=False)
    async def review(
        request: Request,
        category: str = "all",
        decision: str | None = None,
        review_category: str | None = None,
        sort: str = "id",
        direction: str = "asc",
        page: str = "1",
        page_size: str = "25",
    ) -> Response:
        if not _authenticated(request):
            return _session_error(request, templates)
        explorer = _explorer_snapshot(request)
        if explorer.status != "completed" or explorer.session is None:
            return _render_state(request, templates, explorer)

        try:
            session = _view_session(
                explorer.session,
                category=category,
                decision=decision,
                review_category=review_category,
                sort=sort,
                direction=direction,
                page=page,
                page_size=page_size,
            )
            view = get_review_view(session)
        except ValueError:
            return _review_error(request, templates, "The review view parameters are invalid.", 400)

        summary = summarize_review_session(session)
        conflicts = find_review_conflicts(session)
        response = templates.TemplateResponse(
            request=request,
            name="review.html",
            context=_review_context(
                request,
                explorer,
                session,
                view,
                summary,
                conflicts,
                category=category,
                decision=decision,
                review_category=review_category,
                sort=sort,
                direction=direction,
                page=page,
                page_size=page_size,
            ),
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.get("/review/items/{item_id}", name="review_item", include_in_schema=False)
    async def review_item(request: Request, item_id: str) -> Response:
        if not _authenticated(request):
            return _session_error(request, templates)
        explorer = _explorer_snapshot(request)
        if explorer.status != "completed" or explorer.session is None:
            return _review_error(request, templates, "No completed scan is available.", 404)
        try:
            item = get_review_item(explorer.session, item_id)
        except ValueError:
            return _review_error(request, templates, "That review row was not found.", 404)

        metadata = get_review_item_metadata(explorer.session, item.id)
        source = item.plan_item.source
        size_bytes = metadata.size_bytes
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
                "decision_label": _DECISION_LABELS.get(item.decision, item.decision),
                "source_relative": _relative_path(source, explorer.session.root),
                "destination_relative": _relative_path(
                    item.plan_item.destination,
                    explorer.session.root,
                ),
                "size_bytes": size_bytes,
                "modified_time": modified_time,
            },
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.get("/review/conflicts", name="review_conflicts", include_in_schema=False)
    async def review_conflicts(request: Request) -> Response:
        if not _authenticated(request):
            return _session_error(request, templates)
        explorer = _explorer_snapshot(request)
        if explorer.status != "completed" or explorer.session is None:
            return _render_state(request, templates, explorer)
        conflicts = find_review_conflicts(explorer.session)
        response = templates.TemplateResponse(
            request=request,
            name="review_conflicts.html",
            context={
                "conflicts": conflicts,
                "locked_root": request.app.state.web_config.root,
            },
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return router


def _view_session(
    session,
    *,
    category: str,
    decision: str | None,
    review_category: str | None,
    sort: str,
    direction: str,
    page: str,
    page_size: str,
):
    if category not in _CATEGORY_LABELS:
        raise ValueError("invalid category")
    if category != "all":
        session = update_review_filter(session, "category", category)
    if decision is not None:
        session = update_review_filter(session, "decision", decision)
    if review_category is not None:
        session = update_review_filter(session, "review_category", review_category)
    session = update_review_sort(session, sort, direction)
    session = update_review_page_size(session, page_size)
    try:
        requested_page = int(page)
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


def _review_context(
    request: Request,
    explorer: ReviewExplorerSnapshot,
    session,
    view,
    summary: dict[str, int],
    conflicts,
    **query: str | None,
) -> dict[str, object]:
    category = query["category"] or "all"
    filters = dict(session.view_state.filters)
    return {
        "locked_root": request.app.state.web_config.root,
        "explorer": explorer,
        "session": session,
        "view": view,
        "summary": summary,
        "category_counts": review_category_counts(session),
        "category_labels": _CATEGORY_LABELS,
        "decision_labels": _DECISION_LABELS,
        "active_category": category,
        "active_filters": filters,
        "conflicts": conflicts,
                "warning_count": len(explorer.warnings),
                "row_metadata": {
                    row.id: get_review_item_metadata(session, row.id)
                    for row in view.rows
                },
    }


def _explorer_snapshot(request: Request) -> ReviewExplorerSnapshot:
    store: ReviewExplorerStore = request.app.state.review_explorer
    return store.snapshot(request.app.state.scan_jobs.snapshot())


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
        "This bootAI session is not available. Launch bootAI again from the local application.",
        403,
    )


def _authenticated(request: Request) -> bool:
    from organizer.web.security import is_authenticated

    return is_authenticated(request.session)


def _relative_path(path, root) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
