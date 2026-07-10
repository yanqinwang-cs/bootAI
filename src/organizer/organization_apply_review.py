from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from organizer.executor import apply_move_plan
from organizer.models import MovePlanItem, OperationLog
from organizer.organization_review import (
    DECISION_APPROVE,
    load_organization_review,
    resolve_organization_review_path,
)
from organizer.reports import validate_report_output_path

CONFIRM_APPLY_ORGANIZATION_REVIEW = "APPLY ORGANIZATION REVIEW"
ORGANIZATION_REVIEW_APPLY_SCHEMA_VERSION = 1
ORGANIZATION_REVIEW_APPLY_SOURCE = (
    "bootAI Stage 10.9 organization review apply result"
)
DEFAULT_ORGANIZATION_REVIEW_APPLY_RESULT_PATH = (
    Path("AI_Review")
    / "reviews"
    / "organization_review_apply_result.json"
)


@dataclass(frozen=True)
class OrganizationReviewApplyOutcome:
    result_path: Path
    operation_log: OperationLog | None
    approved_count: int
    applied_count: int
    skipped_count: int
    failed_count: int
    warnings: tuple[str, ...]


def apply_approved_organization_review(
    review_path: Path,
    root: Path,
    confirmation: str,
) -> OrganizationReviewApplyOutcome:
    if confirmation != CONFIRM_APPLY_ORGANIZATION_REVIEW:
        raise ValueError("exact organization review confirmation is required")

    resolved_root = root.resolve()
    resolved_review_path = resolve_organization_review_path(
        review_path,
        resolved_root,
    )
    review = load_organization_review(resolved_review_path, resolved_root)
    raw_items = review["items"]
    if not isinstance(raw_items, list):
        raise ValueError("organization review items must be a list")

    approved_rows = [
        item
        for item in raw_items
        if isinstance(item, dict) and item.get("decision") == DECISION_APPROVE
    ]
    skipped = [
        {
            "review_id": item["review_id"],
            "decision": item["decision"],
            "reason": "decision was not approve",
        }
        for item in raw_items
        if isinstance(item, dict) and item.get("decision") != DECISION_APPROVE
    ]

    _validate_approved_conflicts(approved_rows, resolved_root)
    plan_items = [_row_to_plan_item(row, resolved_root) for row in approved_rows]
    result_path = _next_result_path(resolved_root)
    validate_report_output_path(result_path, resolved_root)

    if not plan_items:
        result = _build_apply_result(
            review_file=resolved_review_path,
            root=resolved_root,
            approved_rows=approved_rows,
            skipped=skipped,
            operation_log=None,
        )
        _write_apply_result(result_path, result)
        return _outcome(result_path, None, result)

    operation_log = apply_move_plan(plan_items, resolved_root)
    result = _build_apply_result(
        review_file=resolved_review_path,
        root=resolved_root,
        approved_rows=approved_rows,
        skipped=skipped,
        operation_log=operation_log,
    )
    _write_apply_result(result_path, result)
    return _outcome(result_path, operation_log, result)


def _validate_approved_conflicts(
    approved_rows: list[dict[str, Any]],
    root: Path,
) -> None:
    source_ids: dict[str, list[str]] = {}
    destination_ids: dict[str, list[str]] = {}
    for row in approved_rows:
        review_id = str(row["review_id"])
        source = _normalized_root_relative_path(str(row["source"]), root)
        destination = _normalized_root_relative_path(
            str(row["destination"]),
            root,
        )
        source_ids.setdefault(source, []).append(review_id)
        destination_ids.setdefault(destination, []).append(review_id)

    source_conflicts = {
        path: ids for path, ids in source_ids.items() if len(ids) > 1
    }
    if source_conflicts:
        path, ids = sorted(source_conflicts.items())[0]
        raise ValueError(
            f"approved source conflict for {path}: {', '.join(sorted(ids))}"
        )

    destination_conflicts = {
        path: ids for path, ids in destination_ids.items() if len(ids) > 1
    }
    if destination_conflicts:
        path, ids = sorted(destination_conflicts.items())[0]
        raise ValueError(
            f"approved destination conflict for {path}: {', '.join(sorted(ids))}"
        )


def _row_to_plan_item(row: dict[str, Any], root: Path) -> MovePlanItem:
    source = root / Path(str(row["source"]))
    destination = root / Path(str(row["destination"]))
    return MovePlanItem(
        source=source,
        destination=destination,
        reason=str(row["reason"]),
        confidence=int(row["confidence"]),
        operation="dry-run move",
        overwrite_risk=bool(row["overwrite_risk"]),
    )


def _build_apply_result(
    review_file: Path,
    root: Path,
    approved_rows: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    operation_log: OperationLog | None,
) -> dict[str, Any]:
    applied: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    warnings: list[str] = []
    operation_count = 0

    if operation_log is not None:
        operation_count = len(operation_log.operations)
        for row, operation in zip(approved_rows, operation_log.operations):
            record = _result_record(row)
            if operation.success:
                applied.append(record)
            else:
                failed.append({**record, "message": operation.message})

    if operation_count < len(approved_rows):
        unattempted = approved_rows[operation_count:]
        skipped.extend(
            {
                "review_id": row["review_id"],
                "decision": row["decision"],
                "reason": "approved row was not attempted after an earlier movement failure",
            }
            for row in unattempted
        )
        if operation_log is not None:
            warnings.append(
                f"{len(unattempted)} approved row(s) were not attempted after "
                "an earlier movement failure."
            )

    undo_log_path = None
    if operation_log is not None:
        undo_log_path = _relative_path(operation_log.log_path, root)

    return {
        "schema_version": ORGANIZATION_REVIEW_APPLY_SCHEMA_VERSION,
        "source": ORGANIZATION_REVIEW_APPLY_SOURCE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_file": _relative_path(review_file, root),
        "confirmation": CONFIRM_APPLY_ORGANIZATION_REVIEW,
        "approved_count": len(approved_rows),
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "undo_log_path": undo_log_path,
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
        "warnings": warnings,
    }


def _result_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_id": row["review_id"],
        "source": row["source"],
        "destination": row["destination"],
        "anchor": row["anchor"],
        "risk_level": row["risk_level"],
    }


def _normalized_root_relative_path(path_text: str, root: Path) -> str:
    return (root / Path(path_text)).relative_to(root).as_posix()


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _next_result_path(root: Path) -> Path:
    base = root / DEFAULT_ORGANIZATION_REVIEW_APPLY_RESULT_PATH
    if not os.path.lexists(base):
        return base
    for counter in range(1, 1000):
        candidate = base.with_name(f"{base.stem}_{counter}{base.suffix}")
        if not os.path.lexists(candidate):
            return candidate
    raise ValueError(f"could not find unused apply-result path for {base}")


def _write_apply_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2, sort_keys=True)
        file.write("\n")


def _outcome(
    result_path: Path,
    operation_log: OperationLog | None,
    result: dict[str, Any],
) -> OrganizationReviewApplyOutcome:
    return OrganizationReviewApplyOutcome(
        result_path=result_path,
        operation_log=operation_log,
        approved_count=int(result["approved_count"]),
        applied_count=int(result["applied_count"]),
        skipped_count=int(result["skipped_count"]),
        failed_count=int(result["failed_count"]),
        warnings=tuple(str(warning) for warning in result["warnings"]),
    )
