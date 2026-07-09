from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from organizer.duplicates import find_exact_duplicates
from organizer.grouping import build_organization_suggestions, find_project_groups
from organizer.models import FileMetadata, MovePlanItem, OrganizationSuggestion, ReviewedPlanItem
from organizer.planner import build_duplicate_review_plan
from organizer.review import build_review_candidate_plan, detect_review_candidates
from organizer.safety import validate_under_root

REVIEW_SESSION_SCHEMA_VERSION = 1
REVIEW_PLAN_TYPE = "batch_review"
DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"
CATEGORY_DUPLICATE = "duplicate"
CATEGORY_ORGANIZATION = "organization"
CATEGORY_REVIEW_CANDIDATE = "review_candidate"
REVIEW_CANDIDATE_CATEGORIES = {"empty", "temporary", "backup_or_copy"}
CONFLICT_SOURCE = "source"
CONFLICT_DESTINATION = "destination"
MEMORY_NEW = "new_suggestion"
MEMORY_REJECTED = "rejected_remembered"
MEMORY_APPROVED = "approved_remembered"
MEMORY_STALE = "stale_prior_decision"


@dataclass(frozen=True)
class ReviewedPlanConflict:
    conflict_type: str
    relative_path: str
    items: list[ReviewedPlanItem]


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
    review_candidates = detect_review_candidates(files)
    review_candidate_plan_items = build_review_candidate_plan(
        review_candidates,
        resolved_root,
    )

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
    items.extend(
        _items_for_review_candidate_plan(
            review_candidate_plan_items,
            [candidate.category for candidate in review_candidates],
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


def summarize_review_items(
    items: list[ReviewedPlanItem],
    root: Path | None = None,
) -> dict[str, int]:
    duplicate_approved = _count(items, CATEGORY_DUPLICATE, DECISION_APPROVED)
    duplicate_rejected = _count(items, CATEGORY_DUPLICATE, DECISION_REJECTED)
    organization_approved = _count(items, CATEGORY_ORGANIZATION, DECISION_APPROVED)
    organization_rejected = _count(items, CATEGORY_ORGANIZATION, DECISION_REJECTED)
    review_candidate_approved = _count(
        items,
        CATEGORY_REVIEW_CANDIDATE,
        DECISION_APPROVED,
    )
    review_candidate_rejected = _count(
        items,
        CATEGORY_REVIEW_CANDIDATE,
        DECISION_REJECTED,
    )
    conflicts = find_approved_move_conflicts(items, root) if root is not None else []
    source_conflicts = [
        conflict
        for conflict in conflicts
        if conflict.conflict_type == CONFLICT_SOURCE
    ]
    destination_conflicts = [
        conflict
        for conflict in conflicts
        if conflict.conflict_type == CONFLICT_DESTINATION
    ]
    return {
        "approved_move_count": (
            duplicate_approved
            + organization_approved
            + review_candidate_approved
        ),
        "rejected_move_count": (
            duplicate_rejected
            + organization_rejected
            + review_candidate_rejected
        ),
        "duplicate_approved_move_count": duplicate_approved,
        "duplicate_rejected_move_count": duplicate_rejected,
        "organization_approved_move_count": organization_approved,
        "organization_rejected_move_count": organization_rejected,
        "review_candidate_approved_move_count": review_candidate_approved,
        "review_candidate_rejected_move_count": review_candidate_rejected,
        "approved_source_conflict_count": len(source_conflicts),
        "approved_destination_conflict_count": len(destination_conflicts),
        "approved_move_conflict_count": len(conflicts),
        "memory_new_suggestion_count": _memory_count(items, MEMORY_NEW),
        "memory_rejected_remembered_count": _memory_count(items, MEMORY_REJECTED),
        "memory_approved_remembered_count": _memory_count(items, MEMORY_APPROVED),
        "memory_stale_prior_decision_count": _memory_count(items, MEMORY_STALE),
    }


def approved_plan_items(items: list[ReviewedPlanItem]) -> list[MovePlanItem]:
    return [
        item.plan_item
        for item in items
        if item.decision == DECISION_APPROVED
    ]


def find_approved_move_conflicts(
    items: list[ReviewedPlanItem],
    root: Path,
) -> list[ReviewedPlanConflict]:
    source_groups = _approved_items_by_path(items, root, CONFLICT_SOURCE)
    destination_groups = _approved_items_by_path(items, root, CONFLICT_DESTINATION)

    conflicts = [
        ReviewedPlanConflict(
            conflict_type=CONFLICT_SOURCE,
            relative_path=relative_path,
            items=_sort_review_items(conflict_items),
        )
        for relative_path, conflict_items in source_groups.items()
        if len(conflict_items) > 1
    ]
    conflicts.extend(
        ReviewedPlanConflict(
            conflict_type=CONFLICT_DESTINATION,
            relative_path=relative_path,
            items=_sort_review_items(conflict_items),
        )
        for relative_path, conflict_items in destination_groups.items()
        if len(conflict_items) > 1
    )
    return sorted(
        conflicts,
        key=lambda conflict: (
            0 if conflict.conflict_type == CONFLICT_SOURCE else 1,
            conflict.relative_path,
        ),
    )


def validate_no_approved_move_conflicts(
    items: list[ReviewedPlanItem],
    root: Path,
) -> None:
    conflicts = find_approved_move_conflicts(items, root)
    if conflicts:
        raise ValueError(
            "reviewed plan has approved move conflicts; reject conflicting "
            "approved moves before applying"
        )


def load_reviewed_plan_move_items(
    plan_path: Path,
    root: Path,
) -> list[MovePlanItem]:
    resolved_root = root.resolve()
    resolved_plan_path = _validate_existing_reviewed_plan_path(plan_path, resolved_root)

    try:
        with resolved_plan_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid reviewed plan JSON: {error}") from error

    return reviewed_plan_data_to_move_items(data, resolved_root)


def reviewed_plan_data_to_move_items(
    data: object,
    root: Path,
) -> list[MovePlanItem]:
    if not isinstance(data, dict):
        raise ValueError("reviewed plan must contain a JSON object")
    if data.get("schema_version") != REVIEW_SESSION_SCHEMA_VERSION:
        raise ValueError("reviewed plan schema_version must be 1")
    if data.get("plan_type") != REVIEW_PLAN_TYPE:
        raise ValueError('reviewed plan plan_type must be "batch_review"')

    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("reviewed plan items must be a list")

    reviewed_items: list[ReviewedPlanItem] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"reviewed plan item {index} must be an object")
        _validate_saved_item_identity(item, index)
        if item["decision"] == DECISION_REJECTED:
            continue

        source = _validated_relative_path(item.get("source"), "source", index)
        destination = _validated_relative_path(item.get("destination"), "destination", index)
        source_path = root / source
        destination_path = root / destination
        validate_under_root(source_path.resolve(strict=False), root)
        validate_under_root(destination_path.resolve(strict=False), root)

        reviewed_items.append(
            ReviewedPlanItem(
                id=item["id"].strip().upper(),
                category=item["category"],
                decision=DECISION_APPROVED,
                review_category=_optional_review_category(item),
                plan_item=MovePlanItem(
                    source=source_path,
                    destination=destination_path,
                    reason=_optional_string(item.get("reason"), "Approved reviewed plan item."),
                    confidence=_optional_confidence(item.get("confidence")),
                    operation=_optional_string(item.get("operation"), "dry-run move"),
                    overwrite_risk=_optional_bool(
                        item.get("overwrite_risk"),
                        destination_path.exists(),
                    ),
                ),
            )
        )
    validate_no_approved_move_conflicts(reviewed_items, root)
    return approved_plan_items(reviewed_items)


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
        "summary": summarize_review_items(items, resolved_root),
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


def _items_for_review_candidate_plan(
    plan_items: list[MovePlanItem],
    review_categories: list[str],
) -> list[ReviewedPlanItem]:
    return [
        ReviewedPlanItem(
            id=f"R{index}",
            category=CATEGORY_REVIEW_CANDIDATE,
            plan_item=plan_item,
            decision=DECISION_APPROVED,
            review_category=review_category,
        )
        for index, (plan_item, review_category) in enumerate(
            zip(plan_items, review_categories),
            start=1,
        )
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
        replace(
            item,
            decision=decision,
            memory_status=MEMORY_NEW,
            remembered_decision=None,
        )
        if item.id in ids_to_update
        else item
        for item in items
    ]


def _approved_items_by_path(
    items: list[ReviewedPlanItem],
    root: Path,
    conflict_type: str,
) -> dict[str, list[ReviewedPlanItem]]:
    grouped: dict[str, list[ReviewedPlanItem]] = {}
    for item in items:
        if item.decision != DECISION_APPROVED:
            continue
        path = (
            item.plan_item.source
            if conflict_type == CONFLICT_SOURCE
            else item.plan_item.destination
        )
        relative_path = _normalized_relative_path(path, root)
        grouped.setdefault(relative_path, []).append(item)
    return grouped


def _normalized_relative_path(path: Path, root: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve(strict=False)
    validate_under_root(resolved_path, resolved_root)
    return resolved_path.relative_to(resolved_root).as_posix()


def _sort_review_items(items: list[ReviewedPlanItem]) -> list[ReviewedPlanItem]:
    return sorted(items, key=lambda item: item.id)


def _validate_existing_reviewed_plan_path(path: Path, root: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    resolved_path = validate_under_root(candidate.resolve(strict=False), root)
    if candidate.is_symlink():
        validate_under_root(candidate.resolve(), root)
    if not candidate.exists():
        raise ValueError(f"reviewed plan does not exist: {path}")
    if not candidate.is_file():
        raise ValueError(f"reviewed plan is not a file: {path}")
    return resolved_path


def _validate_saved_item_identity(item: dict[str, Any], index: int) -> None:
    item_id = item.get("id")
    category = item.get("category")
    decision = item.get("decision")
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError(f"reviewed plan item {index} id must be a non-empty string")
    if category not in {
        CATEGORY_DUPLICATE,
        CATEGORY_ORGANIZATION,
        CATEGORY_REVIEW_CANDIDATE,
    }:
        raise ValueError(f"reviewed plan item {index} category is invalid")
    if decision not in {DECISION_APPROVED, DECISION_REJECTED}:
        raise ValueError(f"reviewed plan item {index} decision is invalid")
    if category == CATEGORY_REVIEW_CANDIDATE:
        review_category = item.get("review_category")
        if review_category not in REVIEW_CANDIDATE_CATEGORIES:
            raise ValueError(f"reviewed plan item {index} review_category is invalid")


def _validated_relative_path(
    value: object,
    field_name: str,
    index: int,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"reviewed plan item {index} {field_name} must be a relative path string")
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"reviewed plan item {index} {field_name} must be relative")
    if any(part == ".." for part in path.parts):
        raise ValueError(f"reviewed plan item {index} {field_name} must not contain path traversal")
    return path


def _optional_string(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return fallback


def _optional_confidence(value: object) -> int:
    if isinstance(value, int) and 0 <= value <= 100:
        return value
    return 100


def _optional_bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    return fallback


def _optional_review_category(item: dict[str, Any]) -> str | None:
    if item.get("category") == CATEGORY_REVIEW_CANDIDATE:
        return item["review_category"]
    return None


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


def _memory_count(
    items: list[ReviewedPlanItem],
    memory_status: str,
) -> int:
    return sum(
        1
        for item in items
        if item.memory_status == memory_status
    )


def _item_to_json(
    item: ReviewedPlanItem,
    root: Path,
) -> dict[str, Any]:
    plan_item = item.plan_item
    data = {
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
    if item.category == CATEGORY_REVIEW_CANDIDATE and item.review_category is not None:
        data["review_category"] = item.review_category
    return data


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
