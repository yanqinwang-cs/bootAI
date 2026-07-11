from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from organizer.application.view_models import (
    ModuleReviewSaveResult,
    ModuleReviewSummary,
    ReviewApplicationSession,
    ReviewDecisionChangeResult,
    ReviewItemMetadata,
    ReviewModule,
    ReviewSaveResult,
)
from organizer.application.view_models import ScanApplicationResult
from organizer.models import ReviewedPlanItem
from organizer.review_session import (
    DECISION_APPROVED,
    DECISION_REJECTED,
    DECISION_UNDECIDED,
    PageDecisionPreview,
    ReviewViewPage,
    ReviewViewState,
    ReviewedPlanConflict,
    apply_page_decision_change as apply_page_decision_change_to_items,
    approve_items,
    build_review_session_items,
    build_review_session_items_from_report,
    build_review_view,
    clamp_review_page,
    clear_review_filters,
    clear_review_sort,
    find_approved_move_conflicts,
    get_item,
    load_reviewed_plan_items,
    preview_page_decision_change,
    reject_items,
    review_decision_snapshot,
    save_resumed_reviewed_plan,
    save_reviewed_plan,
    set_review_filter,
    set_review_page,
    set_review_page_size,
    set_review_sort,
    summarize_review_items,
    undecide_items,
)
from organizer.review_state import (
    MEMORY_APPROVED,
    MEMORY_NEW,
    MEMORY_REJECTED,
    MEMORY_STALE,
    ReviewState,
    apply_review_state_to_items,
    load_review_state,
    save_review_state,
    update_review_state_from_items,
)
from organizer.safety import validate_under_root
from organizer.scanner import scan_directory


_MODULE_CATEGORIES = {
    ReviewModule.DUPLICATES: "duplicate",
    ReviewModule.ORGANIZATION: "organization",
    ReviewModule.ATTENTION: "review_candidate",
}
_MODULE_OUTPUT_NAMES = {
    ReviewModule.DUPLICATES: "duplicate_reviewed_plan.json",
    ReviewModule.ORGANIZATION: "organization_reviewed_plan.json",
    ReviewModule.ATTENTION: "attention_reviewed_plan.json",
}
_FRESH_WEB_DECISIONS = {
    MEMORY_NEW: DECISION_UNDECIDED,
    MEMORY_STALE: DECISION_UNDECIDED,
    MEMORY_APPROVED: DECISION_APPROVED,
    MEMORY_REJECTED: DECISION_REJECTED,
}


def create_review_session(
    root: Path,
    max_depth: int | None = None,
    *,
    ignore_review_state: bool = False,
) -> ReviewApplicationSession:
    resolved_root = root.resolve()
    metadata_items = scan_directory(resolved_root, max_depth=max_depth)
    items = build_review_session_items(metadata_items, resolved_root)

    state: ReviewState | None = None
    if not ignore_review_state:
        state = load_review_state(resolved_root)
        if state.decisions:
            items = apply_review_state_to_items(items, state, resolved_root)

    return _new_session(
        root=resolved_root,
        items=items,
        source_path=None,
        review_state=state,
        persist_review_state=True,
        review_state_ignored=ignore_review_state,
    )


def create_review_session_from_scan_result(
    result: ScanApplicationResult,
) -> ReviewApplicationSession:
    """Create review rows from one completed scan result without rescanning."""
    resolved_root = result.root.resolve()
    items = build_review_session_items_from_report(result.report, resolved_root)
    state = load_review_state(resolved_root)
    if state.decisions:
        items = apply_review_state_to_items(items, state, resolved_root)
    return _new_session(
        root=resolved_root,
        items=items,
        source_path=None,
        review_state=state,
        persist_review_state=True,
        review_state_ignored=False,
    )


def create_fresh_web_review_session_from_scan_result(
    result: ScanApplicationResult,
) -> ReviewApplicationSession:
    """Create a conservative fresh web session without changing legacy defaults."""
    session = create_review_session_from_scan_result(result)
    if session.source_path is not None:
        raise ValueError("fresh web review session must not be resumed")
    items = tuple(
        replace(
            item,
            decision=_FRESH_WEB_DECISIONS.get(
                item.memory_status,
                DECISION_UNDECIDED,
            ),
        )
        for item in session.items
    )
    return replace(
        session,
        items=items,
        saved_decisions=review_decision_snapshot(list(items)),
    )


def review_module_category(module: ReviewModule) -> str:
    return _MODULE_CATEGORIES[_validated_module(module)]


def review_module_items(
    session: ReviewApplicationSession,
    module: ReviewModule,
) -> tuple[ReviewedPlanItem, ...]:
    category = review_module_category(module)
    return tuple(
        sorted(
            (item for item in session.items if item.category == category),
            key=lambda item: item.id,
        )
    )


def summarize_review_module(
    session: ReviewApplicationSession,
    module: ReviewModule,
) -> ModuleReviewSummary:
    validated_module = _validated_module(module)
    items = review_module_items(session, validated_module)
    return ModuleReviewSummary(
        module=validated_module,
        row_count=len(items),
        approved_count=sum(item.decision == DECISION_APPROVED for item in items),
        rejected_count=sum(item.decision == DECISION_REJECTED for item in items),
        undecided_count=sum(item.decision == DECISION_UNDECIDED for item in items),
        conflict_count=len(find_approved_move_conflicts(list(items), session.root)),
    )


def review_module_is_dirty(
    session: ReviewApplicationSession,
    module: ReviewModule,
) -> bool:
    saved = dict(session.saved_decisions)
    return any(
        saved.get(item.id) != item.decision
        for item in review_module_items(session, module)
    )


def dirty_review_modules(
    session: ReviewApplicationSession,
) -> tuple[ReviewModule, ...]:
    return tuple(
        module
        for module in ReviewModule
        if review_module_is_dirty(session, module)
    )


def review_module_saved_path(
    session: ReviewApplicationSession,
    module: ReviewModule,
) -> Path | None:
    return dict(session.module_saved_paths).get(_validated_module(module))


def review_category_counts(session: ReviewApplicationSession) -> dict[str, int]:
    counts = {"duplicate": 0, "organization": 0, "review_candidate": 0}
    for item in session.items:
        counts[item.category] = counts.get(item.category, 0) + 1
    return counts


def resume_review_session(
    root: Path,
    reviewed_plan_path: Path,
) -> ReviewApplicationSession:
    resolved_root = root.resolve()
    items = load_reviewed_plan_items(reviewed_plan_path, resolved_root)
    candidate = (
        reviewed_plan_path
        if reviewed_plan_path.is_absolute()
        else resolved_root / reviewed_plan_path
    )
    return _new_session(
        root=resolved_root,
        items=items,
        source_path=candidate.resolve(strict=False),
        review_state=None,
        persist_review_state=False,
        review_state_ignored=False,
    )


def get_review_view(session: ReviewApplicationSession) -> ReviewViewPage:
    return build_review_view(list(session.items), session.view_state, session.root)


def get_review_item(
    session: ReviewApplicationSession,
    item_id: str,
) -> ReviewedPlanItem:
    return get_item(list(session.items), item_id)


def get_review_item_metadata(
    session: ReviewApplicationSession,
    item_id: str,
) -> ReviewItemMetadata:
    item = get_review_item(session, item_id)
    source = item.plan_item.source
    try:
        if source.is_symlink():
            return ReviewItemMetadata(item=item, size_bytes=None, modified_time=None)
        resolved_source = validate_under_root(
            source.resolve(strict=False),
            session.root,
        )
        if not resolved_source.is_file():
            return ReviewItemMetadata(item=item, size_bytes=None, modified_time=None)
        stat = resolved_source.stat()
    except (OSError, ValueError):
        return ReviewItemMetadata(item=item, size_bytes=None, modified_time=None)
    return ReviewItemMetadata(
        item=item,
        size_bytes=stat.st_size,
        modified_time=stat.st_mtime,
    )


def get_review_source_key(
    session: ReviewApplicationSession,
    item_id: str,
) -> str:
    item = get_review_item(session, item_id)
    resolved_source = validate_under_root(
        item.plan_item.source.resolve(strict=False),
        session.root,
    )
    return resolved_source.relative_to(session.root).as_posix()


def update_review_filter(
    session: ReviewApplicationSession,
    field: str,
    value: str,
) -> ReviewApplicationSession:
    return replace(
        session,
        view_state=set_review_filter(session.view_state, field, value),
    )


def clear_review_session_filters(
    session: ReviewApplicationSession,
) -> ReviewApplicationSession:
    return replace(session, view_state=clear_review_filters(session.view_state))


def update_review_sort(
    session: ReviewApplicationSession,
    field: str,
    direction: str = "asc",
) -> ReviewApplicationSession:
    return replace(
        session,
        view_state=set_review_sort(session.view_state, field, direction),
    )


def clear_review_session_sort(
    session: ReviewApplicationSession,
) -> ReviewApplicationSession:
    return replace(session, view_state=clear_review_sort(session.view_state))


def update_review_page(
    session: ReviewApplicationSession,
    page_request: str,
) -> ReviewApplicationSession:
    return replace(
        session,
        view_state=set_review_page(
            session.view_state,
            page_request,
            list(session.items),
            session.root,
        ),
    )


def update_review_page_size(
    session: ReviewApplicationSession,
    page_size_text: str,
) -> ReviewApplicationSession:
    return replace(
        session,
        view_state=set_review_page_size(session.view_state, page_size_text),
    )


def change_review_decisions(
    session: ReviewApplicationSession,
    ids: list[str] | tuple[str, ...],
    decision: str,
) -> ReviewDecisionChangeResult:
    normalized_ids = tuple(dict.fromkeys(item_id.upper() for item_id in ids))
    before = {item.id: item.decision for item in session.items}
    items = list(session.items)

    if decision == DECISION_APPROVED:
        updated_items = approve_items(items, list(normalized_ids))
    elif decision == DECISION_REJECTED:
        updated_items = reject_items(items, list(normalized_ids))
    elif decision == DECISION_UNDECIDED:
        updated_items = undecide_items(items, list(normalized_ids))
    else:
        raise ValueError(f"unsupported review decision: {decision}")

    changed_ids = tuple(
        item_id
        for item_id in normalized_ids
        if before[item_id] != decision
    )
    idempotent_ids = tuple(
        item_id
        for item_id in normalized_ids
        if before[item_id] == decision
    )
    view_state = clamp_review_page(
        session.view_state,
        updated_items,
        session.root,
    )
    updated_session = replace(
        session,
        items=tuple(updated_items),
        view_state=view_state,
        saved_plan_path=None if changed_ids else session.saved_plan_path,
    )
    return ReviewDecisionChangeResult(
        session=updated_session,
        decision=decision,
        changed_ids=changed_ids,
        idempotent_ids=idempotent_ids,
    )


def preview_current_page_decision(
    session: ReviewApplicationSession,
    decision: str,
) -> PageDecisionPreview:
    return preview_page_decision_change(
        list(session.items),
        session.view_state,
        session.root,
        decision,
    )


def apply_current_page_decision(
    session: ReviewApplicationSession,
    preview: PageDecisionPreview,
) -> ReviewDecisionChangeResult:
    updated_items = apply_page_decision_change_to_items(list(session.items), preview)
    view_state = clamp_review_page(
        session.view_state,
        updated_items,
        session.root,
    )
    updated_session = replace(
        session,
        items=tuple(updated_items),
        view_state=view_state,
        saved_plan_path=(
            None if preview.change_ids else session.saved_plan_path
        ),
    )
    idempotent_ids = tuple(
        item_id
        for item_id in preview.target_ids
        if item_id not in set(preview.change_ids)
    )
    return ReviewDecisionChangeResult(
        session=updated_session,
        decision=preview.decision,
        changed_ids=preview.change_ids,
        idempotent_ids=idempotent_ids,
    )


def summarize_review_session(
    session: ReviewApplicationSession,
) -> dict[str, int]:
    return summarize_review_items(list(session.items), session.root)


def find_review_conflicts(
    session: ReviewApplicationSession,
) -> tuple[ReviewedPlanConflict, ...]:
    return tuple(find_approved_move_conflicts(list(session.items), session.root))


def save_review_module(
    session: ReviewApplicationSession,
    module: ReviewModule,
) -> ModuleReviewSaveResult:
    validated_module = _validated_module(module)
    items = list(review_module_items(session, validated_module))
    if not items:
        raise ValueError("review module has no rows to save")
    reviewed_plan_path = save_reviewed_plan(
        items,
        session.root,
        output_name=_MODULE_OUTPUT_NAMES[validated_module],
    )

    state = session.review_state
    review_state_path: Path | None = None
    if session.persist_review_state:
        if state is None:
            state = load_review_state(session.root)
        state = update_review_state_from_items(state, items, session.root)
        review_state_path = save_review_state(state, session.root)

    saved_decisions = dict(session.saved_decisions)
    saved_decisions.update((item.id, item.decision) for item in items)
    module_paths = dict(session.module_saved_paths)
    module_paths[validated_module] = reviewed_plan_path
    updated_session = replace(
        session,
        review_state=state,
        saved_decisions=tuple(sorted(saved_decisions.items())),
        module_saved_paths=tuple(
            sorted(module_paths.items(), key=lambda pair: pair[0].value)
        ),
    )
    return ModuleReviewSaveResult(
        session=updated_session,
        module=validated_module,
        reviewed_plan_path=reviewed_plan_path,
        review_state_path=review_state_path,
        summary=summarize_review_module(updated_session, validated_module),
    )


def save_review_session(session: ReviewApplicationSession) -> ReviewSaveResult:
    items = list(session.items)
    if session.source_path is None:
        reviewed_plan_path = save_reviewed_plan(items, session.root)
    else:
        reviewed_plan_path = save_resumed_reviewed_plan(
            items,
            session.root,
            session.source_path,
        )

    state = session.review_state
    review_state_path: Path | None = None
    if session.persist_review_state:
        if state is None:
            state = load_review_state(session.root)
        state = update_review_state_from_items(state, items, session.root)
        review_state_path = save_review_state(state, session.root)

    updated_session = replace(
        session,
        saved_plan_path=reviewed_plan_path,
        review_state=state,
        saved_decisions=review_decision_snapshot(items),
    )
    return ReviewSaveResult(
        session=updated_session,
        reviewed_plan_path=reviewed_plan_path,
        review_state_path=review_state_path,
    )


def _new_session(
    *,
    root: Path,
    items: list[ReviewedPlanItem],
    source_path: Path | None,
    review_state: ReviewState | None,
    persist_review_state: bool,
    review_state_ignored: bool,
) -> ReviewApplicationSession:
    item_tuple = tuple(items)
    return ReviewApplicationSession(
        root=root,
        items=item_tuple,
        view_state=ReviewViewState(),
        source_path=source_path,
        saved_plan_path=None,
        review_state=review_state,
        persist_review_state=persist_review_state,
        review_state_ignored=review_state_ignored,
        saved_decisions=tuple(
            sorted((item.id, item.decision) for item in item_tuple)
        ),
    )


def _validated_module(module: ReviewModule) -> ReviewModule:
    if not isinstance(module, ReviewModule):
        raise ValueError("unsupported review module")
    return module
