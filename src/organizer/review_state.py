from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from organizer.models import ReviewedPlanItem
from organizer.safety import validate_under_root

REVIEW_STATE_SCHEMA_VERSION = 1
REVIEW_STATE_FOLDER_NAME = "review_state"
REVIEW_STATE_FILE_NAME = "review_decisions.json"

DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"
CATEGORY_DUPLICATE = "duplicate"
CATEGORY_ORGANIZATION = "organization"
CATEGORY_REVIEW_CANDIDATE = "review_candidate"
REVIEW_CANDIDATE_CATEGORIES = {"empty", "temporary", "backup_or_copy"}

MEMORY_NEW = "new_suggestion"
MEMORY_REJECTED = "rejected_remembered"
MEMORY_APPROVED = "approved_remembered"
MEMORY_STALE = "stale_prior_decision"


@dataclass(frozen=True)
class ReviewDecisionRecord:
    decision_id: str
    created_at: str
    updated_at: str
    decision: str
    category: str
    review_category: str | None
    source: Path
    destination: Path
    reason: str
    fingerprint: dict[str, int]


@dataclass(frozen=True)
class ReviewState:
    decisions: list[ReviewDecisionRecord]


def review_state_path(root: Path, review_folder_name: str = "AI_Review") -> Path:
    return root.resolve() / review_folder_name / REVIEW_STATE_FOLDER_NAME / REVIEW_STATE_FILE_NAME


def load_review_state(root: Path, review_folder_name: str = "AI_Review") -> ReviewState:
    path = review_state_path(root, review_folder_name)
    if not path.exists():
        return ReviewState(decisions=[])
    resolved_path = validate_under_root(path.resolve(strict=False), root.resolve())
    if path.is_symlink():
        validate_under_root(path.resolve(), root.resolve())
    if not resolved_path.is_file():
        raise ValueError(f"review state is not a file: {path}")

    try:
        with resolved_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid review state JSON: {error}") from error

    return review_state_from_json_data(data)


def review_state_from_json_data(data: object) -> ReviewState:
    if not isinstance(data, dict):
        raise ValueError("review state must contain a JSON object")
    if data.get("schema_version") != REVIEW_STATE_SCHEMA_VERSION:
        raise ValueError("review state schema_version must be 1")

    decisions = data.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("review state decisions must be a list")

    return ReviewState(
        decisions=[
            _record_from_json(record, index)
            for index, record in enumerate(decisions, start=1)
        ],
    )


def save_review_state(
    state: ReviewState,
    root: Path,
    review_folder_name: str = "AI_Review",
) -> Path:
    destination = review_state_path(root, review_folder_name)
    resolved_root = root.resolve()
    resolved_destination = validate_under_root(destination.resolve(strict=False), resolved_root)
    existing_parent = _nearest_existing_parent(destination.parent)
    validate_under_root(existing_parent.resolve(), resolved_root)
    if not existing_parent.is_dir():
        raise ValueError(f"review state parent is not a directory: {existing_parent}")

    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    with resolved_destination.open("w", encoding="utf-8") as file:
        json.dump(review_state_to_json_data(state), file, indent=2, sort_keys=True)
        file.write("\n")
    return resolved_destination


def review_state_to_json_data(state: ReviewState) -> dict[str, Any]:
    return {
        "schema_version": REVIEW_STATE_SCHEMA_VERSION,
        "decisions": [
            _record_to_json(record)
            for record in sorted(
                state.decisions,
                key=lambda record: (
                    record.category,
                    record.review_category or "",
                    record.source.as_posix(),
                    record.destination.as_posix(),
                    record.decision_id,
                ),
            )
        ],
    }


def apply_review_state_to_items(
    items: list[ReviewedPlanItem],
    state: ReviewState,
    root: Path,
) -> list[ReviewedPlanItem]:
    records_by_key = {
        _record_key(record): record
        for record in state.decisions
    }

    remembered_items: list[ReviewedPlanItem] = []
    for item in items:
        current_key = _item_key(item, root)
        record = records_by_key.get(current_key)
        if record is None:
            remembered_items.append(replace(item, memory_status=MEMORY_NEW, remembered_decision=None))
            continue

        current_fingerprint = _fingerprint_for_path(item.plan_item.source)
        if current_fingerprint is None:
            remembered_items.append(replace(item, memory_status=MEMORY_NEW, remembered_decision=None))
            continue

        if current_fingerprint == record.fingerprint:
            remembered_items.append(
                replace(
                    item,
                    decision=record.decision,
                    memory_status=(
                        MEMORY_REJECTED
                        if record.decision == DECISION_REJECTED
                        else MEMORY_APPROVED
                    ),
                    remembered_decision=record.decision,
                )
            )
        else:
            remembered_items.append(
                replace(
                    item,
                    memory_status=MEMORY_STALE,
                    remembered_decision=record.decision,
                )
            )
    return remembered_items


def update_review_state_from_items(
    state: ReviewState,
    items: list[ReviewedPlanItem],
    root: Path,
) -> ReviewState:
    existing_records = {
        _record_key(record): record
        for record in state.decisions
    }
    updated_records = dict(existing_records)
    timestamp = _utc_timestamp()
    next_counter = len(existing_records) + 1

    for item in sorted(items, key=lambda review_item: review_item.id):
        if not _should_persist_item(item):
            continue
        fingerprint = _fingerprint_for_path(item.plan_item.source)
        if fingerprint is None:
            continue

        key = _item_key(item, root)
        existing = existing_records.get(key)
        if existing is None:
            record = ReviewDecisionRecord(
                decision_id=f"{timestamp}-{next_counter:03d}",
                created_at=timestamp,
                updated_at=timestamp,
                decision=item.decision,
                category=item.category,
                review_category=item.review_category,
                source=Path(key[2]),
                destination=Path(key[3]),
                reason=_state_reason_for_item(item),
                fingerprint=fingerprint,
            )
            next_counter += 1
        else:
            record = replace(
                existing,
                updated_at=timestamp,
                decision=item.decision,
                reason=_state_reason_for_item(item),
                fingerprint=fingerprint,
            )
        updated_records[key] = record

    return ReviewState(
        decisions=sorted(
            updated_records.values(),
            key=lambda record: (
                record.category,
                record.review_category or "",
                record.source.as_posix(),
                record.destination.as_posix(),
                record.decision_id,
            ),
        ),
    )


def _record_from_json(data: object, index: int) -> ReviewDecisionRecord:
    if not isinstance(data, dict):
        raise ValueError(f"review state decision {index} must be an object")

    decision_id = _required_string(data.get("decision_id"), "decision_id", index)
    created_at = _required_string(data.get("created_at"), "created_at", index)
    updated_at = _required_string(data.get("updated_at"), "updated_at", index)
    decision = _required_string(data.get("decision"), "decision", index)
    category = _required_string(data.get("category"), "category", index)
    review_category = data.get("review_category")
    source = _validated_relative_path(data.get("source"), "source", index)
    destination = _validated_relative_path(data.get("destination"), "destination", index)
    reason = _required_string(data.get("reason"), "reason", index)
    fingerprint = _validated_fingerprint(data.get("fingerprint"), index)

    if decision not in {DECISION_APPROVED, DECISION_REJECTED}:
        raise ValueError(f"review state decision {index} decision is invalid")
    if category not in {CATEGORY_DUPLICATE, CATEGORY_ORGANIZATION, CATEGORY_REVIEW_CANDIDATE}:
        raise ValueError(f"review state decision {index} category is invalid")
    if category == CATEGORY_REVIEW_CANDIDATE:
        if review_category not in REVIEW_CANDIDATE_CATEGORIES:
            raise ValueError(f"review state decision {index} review_category is invalid")
    elif review_category is not None:
        raise ValueError(f"review state decision {index} review_category must be null")

    return ReviewDecisionRecord(
        decision_id=decision_id,
        created_at=created_at,
        updated_at=updated_at,
        decision=decision,
        category=category,
        review_category=review_category,
        source=source,
        destination=destination,
        reason=reason,
        fingerprint=fingerprint,
    )


def _record_to_json(record: ReviewDecisionRecord) -> dict[str, Any]:
    return {
        "category": record.category,
        "created_at": record.created_at,
        "decision": record.decision,
        "decision_id": record.decision_id,
        "destination": record.destination.as_posix(),
        "fingerprint": dict(record.fingerprint),
        "reason": record.reason,
        "review_category": record.review_category,
        "source": record.source.as_posix(),
        "updated_at": record.updated_at,
    }


def _required_string(value: object, field_name: str, index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"review state decision {index} {field_name} must be a non-empty string")
    return value.strip()


def _validated_relative_path(value: object, field_name: str, index: int) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"review state decision {index} {field_name} must be a relative path string")
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"review state decision {index} {field_name} must be relative")
    if any(part == ".." for part in path.parts):
        raise ValueError(f"review state decision {index} {field_name} must not contain path traversal")
    return path


def _validated_fingerprint(value: object, index: int) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError(f"review state decision {index} fingerprint must be an object")
    size_bytes = value.get("size_bytes")
    modified_ns = value.get("modified_ns")
    if not isinstance(size_bytes, int) or size_bytes < 0:
        raise ValueError(f"review state decision {index} fingerprint size_bytes is invalid")
    if not isinstance(modified_ns, int) or modified_ns < 0:
        raise ValueError(f"review state decision {index} fingerprint modified_ns is invalid")
    return {"size_bytes": size_bytes, "modified_ns": modified_ns}


def _should_persist_item(item: ReviewedPlanItem) -> bool:
    if item.decision == DECISION_REJECTED:
        return True
    if item.decision != DECISION_APPROVED:
        return False
    return item.category in {CATEGORY_ORGANIZATION, CATEGORY_REVIEW_CANDIDATE}


def _state_reason_for_item(item: ReviewedPlanItem) -> str:
    return f"remembered {item.decision} review decision for {item.id}"


def _item_key(item: ReviewedPlanItem, root: Path) -> tuple[str, str | None, str, str]:
    return (
        item.category,
        item.review_category if item.category == CATEGORY_REVIEW_CANDIDATE else None,
        _relative_to_root(item.plan_item.source, root),
        _relative_to_root(item.plan_item.destination, root),
    )


def _record_key(record: ReviewDecisionRecord) -> tuple[str, str | None, str, str]:
    return (
        record.category,
        record.review_category,
        record.source.as_posix(),
        record.destination.as_posix(),
    )


def _relative_to_root(path: Path, root: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve(strict=False)
    validate_under_root(resolved_path, resolved_root)
    return resolved_path.relative_to(resolved_root).as_posix()


def _fingerprint_for_path(path: Path) -> dict[str, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    if not path.is_file():
        return None
    return {
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def _nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
