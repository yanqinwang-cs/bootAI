from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from organizer.duplicates import find_exact_duplicates
from organizer.grouping import build_organization_suggestions, find_project_groups
from organizer.models import FileMetadata, MovePlanItem, OrganizationSuggestion, ReviewedPlanItem
from organizer.planner import build_duplicate_review_plan
from organizer.safety import validate_under_root

REVIEW_SESSION_SCHEMA_VERSION = 1
REVIEW_PLAN_TYPE = "batch_review"
DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"
CATEGORY_DUPLICATE = "duplicate"
CATEGORY_ORGANIZATION = "organization"


def build_review_session_items(
    files: list[FileMetadata],
    root: Path,
) -> list[ReviewedPlanItem]:
    resolved_root = root.resolve()
    duplicate_groups = find_exact_duplicates(files)
    duplicate_plan_items = build_duplicate_review_plan(duplicate_groups, resolved_root)
    organization_suggestions = build_organization_suggestions(
        find_project_groups(files),
        resolved_root,
    )
    organization_plan_items = _flatten_plan_items(organization_suggestions)

    items: list[ReviewedPlanItem] = []
    items.extend(
        _items_for_plan(
            duplicate_plan_items,
            CATEGORY_DUPLICATE,
            "D",
        )
    )
    items.extend(
        _items_for_plan(
            organization_plan_items,
            CATEGORY_ORGANIZATION,
            "O",
        )
    )
    return items


def approve_items(
    items: list[ReviewedPlanItem],
    ids: list[str],
) -> list[ReviewedPlanItem]:
    return _set_decision(items, ids, DECISION_APPROVED)


def reject_items(
    items: list[ReviewedPlanItem],
    ids: list[str],
) -> list[ReviewedPlanItem]:
    return _set_decision(items, ids, DECISION_REJECTED)


def get_item(
    items: list[ReviewedPlanItem],
    item_id: str,
) -> ReviewedPlanItem:
    normalized_id = item_id.upper()
    for item in items:
        if item.id == normalized_id:
            return item
    raise ValueError(f"unknown review item ID: {item_id}")


def summarize_review_items(items: list[ReviewedPlanItem]) -> dict[str, int]:
    duplicate_approved = _count(items, CATEGORY_DUPLICATE, DECISION_APPROVED)
    duplicate_rejected = _count(items, CATEGORY_DUPLICATE, DECISION_REJECTED)
    organization_approved = _count(items, CATEGORY_ORGANIZATION, DECISION_APPROVED)
    organization_rejected = _count(items, CATEGORY_ORGANIZATION, DECISION_REJECTED)
    return {
        "approved_move_count": duplicate_approved + organization_approved,
        "rejected_move_count": duplicate_rejected + organization_rejected,
        "duplicate_approved_move_count": duplicate_approved,
        "duplicate_rejected_move_count": duplicate_rejected,
        "organization_approved_move_count": organization_approved,
        "organization_rejected_move_count": organization_rejected,
    }


def approved_plan_items(items: list[ReviewedPlanItem]) -> list[MovePlanItem]:
    return [
        item.plan_item
        for item in items
        if item.decision == DECISION_APPROVED
    ]


def reviewed_plan_to_json_data(
    items: list[ReviewedPlanItem],
    root: Path,
) -> dict[str, Any]:
    resolved_root = root.resolve()
    return {
        "schema_version": REVIEW_SESSION_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scan_root": ".",
        "plan_type": REVIEW_PLAN_TYPE,
        "summary": summarize_review_items(items),
        "items": [
            _item_to_json(item, resolved_root)
            for item in sorted(items, key=lambda item: item.id)
        ],
    }


def save_reviewed_plan(
    items: list[ReviewedPlanItem],
    root: Path,
    review_folder_name: str = "AI_Review",
    session_folder_name: str = "review_sessions",
) -> Path:
    resolved_root = root.resolve()
    log_dir = resolved_root / review_folder_name / session_folder_name
    destination = _next_reviewed_plan_path(log_dir)
    resolved_destination = _validate_new_output_path(destination, resolved_root)
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    with resolved_destination.open("x", encoding="utf-8") as file:
        json.dump(reviewed_plan_to_json_data(items, resolved_root), file, indent=2, sort_keys=True)
        file.write("\n")
    return resolved_destination


def _items_for_plan(
    plan_items: list[MovePlanItem],
    category: str,
    prefix: str,
) -> list[ReviewedPlanItem]:
    return [
        ReviewedPlanItem(
            id=f"{prefix}{index}",
            category=category,
            plan_item=plan_item,
            decision=DECISION_APPROVED,
        )
        for index, plan_item in enumerate(plan_items, start=1)
    ]


def _flatten_plan_items(
    suggestions: list[OrganizationSuggestion],
) -> list[MovePlanItem]:
    return [
        item
        for suggestion in suggestions
        for item in suggestion.plan_items
    ]


def _set_decision(
    items: list[ReviewedPlanItem],
    ids: list[str],
    decision: str,
) -> list[ReviewedPlanItem]:
    normalized_ids = [item_id.upper() for item_id in ids]
    known_ids = {item.id for item in items}
    unknown_ids = [item_id for item_id in normalized_ids if item_id not in known_ids]
    if unknown_ids:
        raise ValueError(f"unknown review item ID: {unknown_ids[0]}")

    ids_to_update = set(normalized_ids)
    return [
        replace(item, decision=decision)
        if item.id in ids_to_update
        else item
        for item in items
    ]


def _count(
    items: list[ReviewedPlanItem],
    category: str,
    decision: str,
) -> int:
    return sum(
        1
        for item in items
        if item.category == category and item.decision == decision
    )


def _item_to_json(
    item: ReviewedPlanItem,
    root: Path,
) -> dict[str, Any]:
    plan_item = item.plan_item
    return {
        "id": item.id,
        "category": item.category,
        "decision": item.decision,
        "source": _relative_path(plan_item.source, root),
        "destination": _relative_path(plan_item.destination, root),
        "reason": plan_item.reason,
        "confidence": plan_item.confidence,
        "operation": plan_item.operation,
        "overwrite_risk": plan_item.overwrite_risk,
    }


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _next_reviewed_plan_path(log_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = log_dir / f"{timestamp}_reviewed_plan.json"
    counter = 1
    while os.path.lexists(candidate):
        candidate = log_dir / f"{timestamp}_{counter}_reviewed_plan.json"
        counter += 1
    return candidate


def _validate_new_output_path(path: Path, root: Path) -> Path:
    if os.path.lexists(path):
        raise ValueError(f"reviewed plan already exists: {path}")
    resolved_path = path.resolve(strict=False)
    validate_under_root(resolved_path, root)
    existing_parent = _nearest_existing_parent(path.parent)
    validate_under_root(existing_parent.resolve(), root)
    if not existing_parent.is_dir():
        raise ValueError(f"reviewed plan parent is not a directory: {existing_parent}")
    return resolved_path


def _nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current
