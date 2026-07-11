from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlencode

from organizer.application.review_service import (
    get_review_item_metadata,
    get_review_source_key,
    summarize_review_session,
)
from organizer.application.view_models import ReviewApplicationSession
from organizer.models import ReviewedPlanItem
from organizer.web.formatting import (
    format_bytes,
    format_local_timestamp,
    readable_folder,
)


_PAGE_SIZE = 25
_CATEGORY_PRIORITY = {
    "duplicate": 0,
    "organization": 1,
    "review_candidate": 2,
}
_DECISION_LABELS = {
    "approved": "Chosen",
    "rejected": "Left unchanged",
    "undecided": "Skipped for now",
}
_ATTENTION_REASONS = {
    "empty": "Empty file",
    "temporary": "Temporary-looking file",
    "backup_or_copy": "Backup or copy-looking file",
    "orphan_code": "Code file outside a project folder",
}


class ConsumerSurface(StrEnum):
    HOME = "home"
    DUPLICATES = "duplicates"
    ORGANIZE = "organize"
    ATTENTION = "attention"
    SCANS = "scans"
    ADVANCED = "advanced"


_SURFACE_ROUTES = {
    ConsumerSurface.HOME: "/",
    ConsumerSurface.DUPLICATES: "/duplicates",
    ConsumerSurface.ORGANIZE: "/organize",
    ConsumerSurface.ATTENTION: "/attention",
    ConsumerSurface.SCANS: "/scans",
    ConsumerSurface.ADVANCED: "/review/advanced",
}


@dataclass(frozen=True)
class ConsumerSurfaceSpec:
    surface: ConsumerSurface
    category: str
    page_title: str
    heading: str
    introduction: str
    approved_label: str
    rejected_label: str
    undecided_label: str = "Skip for now"


@dataclass(frozen=True)
class ConsumerSecondaryFinding:
    item_id: str
    module: str
    reason: str
    choice: str


@dataclass(frozen=True)
class ConsumerCard:
    item_id: str
    category: str
    source_key: str
    filename: str
    current_location: str
    suggested_location: str
    reason: str
    duplicate_reference: str | None
    size: str
    modified_time: str
    decision: str
    decision_label: str
    confidence: int
    memory_status: str
    source_relative: str
    destination_relative: str
    secondary_findings: tuple[ConsumerSecondaryFinding, ...]


@dataclass(frozen=True)
class ModuleChoiceSummary:
    key: str
    title: str
    approved_label: str
    approved: int
    rejected_label: str
    rejected: int
    undecided: int


@dataclass(frozen=True)
class ConsumerPlanSummary:
    modules: tuple[ModuleChoiceSummary, ...]
    dirty: bool
    saved_plan_relative: str | None


@dataclass(frozen=True)
class ConsumerPage:
    spec: ConsumerSurfaceSpec
    cards: tuple[ConsumerCard, ...]
    matching_count: int
    page: int
    total_pages: int
    previous_url: str | None
    next_url: str | None


SURFACE_SPECS = {
    ConsumerSurface.DUPLICATES: ConsumerSurfaceSpec(
        surface=ConsumerSurface.DUPLICATES,
        category="duplicate",
        page_title="Duplicates",
        heading="Duplicate copies",
        introduction=(
            "Review files that have exactly matching content. "
            "Planning a choice does not move or remove a file."
        ),
        approved_label="Add to duplicate plan",
        rejected_label="Keep both",
    ),
    ConsumerSurface.ORGANIZE: ConsumerSurfaceSpec(
        surface=ConsumerSurface.ORGANIZE,
        category="organization",
        page_title="Organize",
        heading="Files ready to organize",
        introduction=(
            "Review suggested folders. Your choices remain plans until a "
            "later apply step."
        ),
        approved_label="Add to organization plan",
        rejected_label="Leave here",
    ),
    ConsumerSurface.ATTENTION: ConsumerSurfaceSpec(
        surface=ConsumerSurface.ATTENTION,
        category="review_candidate",
        page_title="Needs attention",
        heading="Files that need attention",
        introduction=(
            "These files may need a closer look. They are not definite "
            "duplicates or organization recommendations."
        ),
        approved_label="Set aside for review",
        rejected_label="Leave here",
    ),
}


def parse_surface(
    value: str | None,
    *,
    allowed: set[ConsumerSurface],
    default: ConsumerSurface,
) -> ConsumerSurface:
    if value is None:
        if default not in allowed:
            raise ValueError("consumer surface is required for this action")
        return default
    try:
        surface = ConsumerSurface(value)
    except ValueError as error:
        raise ValueError("unsupported consumer surface") from error
    if surface not in allowed:
        raise ValueError("consumer surface is unavailable for this action")
    return surface


def surface_url(
    surface: ConsumerSurface,
    *,
    page: int | None = None,
    selected: str | None = None,
    saved: bool = False,
) -> str:
    route = _SURFACE_ROUTES[surface]
    query: dict[str, str] = {}
    if page is not None and surface in SURFACE_SPECS:
        query["page"] = str(page)
    if selected is not None and surface in SURFACE_SPECS:
        query["selected"] = selected
    if saved:
        query["saved"] = "1"
    return f"{route}?{urlencode(query)}" if query else route


def build_consumer_page(
    session: ReviewApplicationSession,
    surface: ConsumerSurface,
    *,
    page: int,
) -> ConsumerPage:
    spec = SURFACE_SPECS[surface]
    all_cards = [
        _build_card(session, items)
        for _, items in _source_groups(session)
        if _primary_item(items).category == spec.category
    ]
    all_cards.sort(key=lambda card: (card.source_key.casefold(), card.item_id))
    matching_count = len(all_cards)
    total_pages = max(1, (matching_count + _PAGE_SIZE - 1) // _PAGE_SIZE)
    if page < 1 or page > total_pages:
        raise ValueError("consumer page is unavailable")
    start = (page - 1) * _PAGE_SIZE
    cards = tuple(all_cards[start : start + _PAGE_SIZE])
    return ConsumerPage(
        spec=spec,
        cards=cards,
        matching_count=matching_count,
        page=page,
        total_pages=total_pages,
        previous_url=surface_url(surface, page=page - 1) if page > 1 else None,
        next_url=(
            surface_url(surface, page=page + 1)
            if page < total_pages
            else None
        ),
    )


def consumer_card_counts(
    session: ReviewApplicationSession,
) -> dict[str, int]:
    counts = {"duplicate": 0, "organization": 0, "review_candidate": 0}
    for _, items in _source_groups(session):
        category = _primary_item(items).category
        counts[category] = counts.get(category, 0) + 1
    return counts


def build_plan_summary(
    session: ReviewApplicationSession,
) -> ConsumerPlanSummary:
    summary = summarize_review_session(session)
    modules = (
        ModuleChoiceSummary(
            key="duplicates",
            title="Duplicates",
            approved_label="Added to plan",
            approved=summary["duplicate_approved_move_count"],
            rejected_label="Keep both",
            rejected=summary["duplicate_rejected_move_count"],
            undecided=summary["duplicate_undecided_move_count"],
        ),
        ModuleChoiceSummary(
            key="organization",
            title="Organization",
            approved_label="Added to plan",
            approved=summary["organization_approved_move_count"],
            rejected_label="Leave here",
            rejected=summary["organization_rejected_move_count"],
            undecided=summary["organization_undecided_move_count"],
        ),
        ModuleChoiceSummary(
            key="attention",
            title="Needs attention",
            approved_label="Set aside for review",
            approved=summary["review_candidate_approved_move_count"],
            rejected_label="Leave here",
            rejected=summary["review_candidate_rejected_move_count"],
            undecided=summary["review_candidate_undecided_move_count"],
        ),
    )
    saved_relative = None
    if session.saved_plan_path is not None:
        try:
            saved_relative = session.saved_plan_path.resolve().relative_to(
                session.root
            ).as_posix()
        except ValueError:
            saved_relative = None
    return ConsumerPlanSummary(
        modules=modules,
        dirty=session.dirty,
        saved_plan_relative=saved_relative,
    )


def feedback_for_card(card: ConsumerCard) -> str:
    if card.decision == "approved":
        if card.category == "review_candidate":
            return "Set aside for review. No file has moved."
        return "Added to your plan. No file has moved yet."
    if card.decision == "rejected":
        return (
            "This file will remain in its current folder. "
            "You can change this choice before applying."
        )
    return "Skipped for now. No final choice has been made."


def card_for_selected(
    page: ConsumerPage,
    selected: str | None,
) -> ConsumerCard | None:
    if selected is None:
        return None
    normalized = selected.upper()
    for card in page.cards:
        if card.item_id == normalized:
            return card
    raise ValueError("selected consumer card is unavailable")


def primary_category_for_item(
    session: ReviewApplicationSession,
    item_id: str,
) -> str:
    normalized = item_id.upper()
    for _, items in _source_groups(session):
        if any(item.id == normalized for item in items):
            return _primary_item(items).category
    raise ValueError("consumer review item is unavailable")


def is_primary_item_for_surface(
    session: ReviewApplicationSession,
    item_id: str,
    surface: ConsumerSurface,
) -> bool:
    spec = SURFACE_SPECS[surface]
    normalized = item_id.upper()
    for _, items in _source_groups(session):
        if any(item.id == normalized for item in items):
            primary = _primary_item(items)
            return primary.id == normalized and primary.category == spec.category
    return False


def _source_groups(
    session: ReviewApplicationSession,
) -> list[tuple[str, tuple[ReviewedPlanItem, ...]]]:
    grouped: dict[str, list[ReviewedPlanItem]] = {}
    for item in session.items:
        key = get_review_source_key(session, item.id)
        grouped.setdefault(key, []).append(item)
    return [
        (key, tuple(sorted(items, key=_item_priority)))
        for key, items in sorted(grouped.items(), key=lambda pair: pair[0].casefold())
    ]


def _primary_item(items: tuple[ReviewedPlanItem, ...]) -> ReviewedPlanItem:
    return min(items, key=_item_priority)


def _item_priority(item: ReviewedPlanItem) -> tuple[int, str]:
    return (_CATEGORY_PRIORITY.get(item.category, 99), item.id)


def _build_card(
    session: ReviewApplicationSession,
    items: tuple[ReviewedPlanItem, ...],
) -> ConsumerCard:
    primary = _primary_item(items)
    metadata = get_review_item_metadata(session, primary.id)
    source_key = get_review_source_key(session, primary.id)
    source_relative = _relative_path(primary.plan_item.source, session.root)
    destination_relative = _relative_path(
        primary.plan_item.destination,
        session.root,
    )
    suggested_location = _suggested_location(primary, session.root)
    secondary = tuple(
        ConsumerSecondaryFinding(
            item_id=item.id,
            module=_module_title(item.category),
            reason=_plain_reason(item, _suggested_location(item, session.root)),
            choice=_module_choice(item),
        )
        for item in items
        if item.id != primary.id
    )
    return ConsumerCard(
        item_id=primary.id,
        category=primary.category,
        source_key=source_key,
        filename=primary.plan_item.source.name,
        current_location=readable_folder(
            primary.plan_item.source.parent,
            session.root,
            include_root=True,
        ),
        suggested_location=suggested_location,
        reason=_plain_reason(primary, suggested_location),
        duplicate_reference=_duplicate_reference(primary),
        size=format_bytes(metadata.size_bytes),
        modified_time=format_local_timestamp(metadata.modified_time),
        decision=primary.decision,
        decision_label=_DECISION_LABELS.get(primary.decision, primary.decision),
        confidence=primary.plan_item.confidence,
        memory_status=primary.memory_status,
        source_relative=source_relative,
        destination_relative=destination_relative,
        secondary_findings=secondary,
    )


def _suggested_location(item: ReviewedPlanItem, root: Path) -> str:
    if item.category == "duplicate":
        return "Duplicate Review"
    if item.category == "review_candidate":
        return "Review area"
    return readable_folder(
        item.plan_item.destination.parent,
        root,
        include_root=False,
    )


def _plain_reason(item: ReviewedPlanItem, suggested_location: str) -> str:
    if item.category == "duplicate":
        reference = _duplicate_reference(item)
        if reference is not None:
            return f"This file has exactly matching content with {reference}."
        return "Another file in this scan has exactly matching content."
    if item.category == "review_candidate":
        return _ATTENTION_REASONS.get(
            item.review_category or "",
            "This file may need a closer look.",
        )
    if suggested_location == "Not available":
        return "bootAI found a possible folder for this file."
    return f"This file appears related to {suggested_location}."


def _duplicate_reference(item: ReviewedPlanItem) -> str | None:
    prefix = "exact duplicate of "
    reason = item.plan_item.reason.strip()
    if not reason.lower().startswith(prefix):
        return None
    reference = reason[len(prefix) :].strip()
    return Path(reference).name if reference else None


def _module_title(category: str) -> str:
    return {
        "duplicate": "Duplicates",
        "organization": "Organization",
        "review_candidate": "Needs attention",
    }.get(category, category.replace("_", " ").title())


def _module_choice(item: ReviewedPlanItem) -> str:
    if item.decision == "undecided":
        return "Skipped for now"
    if item.category == "duplicate":
        return "Added to duplicate plan" if item.decision == "approved" else "Keep both"
    if item.category == "organization":
        return "Added to organization plan" if item.decision == "approved" else "Leave here"
    return "Set aside for review" if item.decision == "approved" else "Leave here"


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return "Not available"
