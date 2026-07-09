from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from organizer.duplicates import find_exact_duplicates
from organizer.grouping import build_organization_suggestions, find_project_groups
from organizer.llm_refinement import (
    build_refined_organization_suggestion,
    refine_project_groups_with_ollama,
)
from organizer.models import (
    DuplicateGroup,
    FileMetadata,
    MovePlanItem,
    OrganizationSuggestion,
    ProjectGroup,
    ReviewCandidate,
)
from organizer.planner import build_duplicate_review_plan
from organizer.review import build_review_candidate_plan, detect_review_candidates
from organizer.safety import validate_under_root
from organizer.scanner import scan_directory

REPORT_SCHEMA_VERSION = 1


def build_scan_report(
    root: Path,
    max_depth: int | None = None,
    refine_groups: bool = False,
    llm_client: object | None = None,
) -> dict[str, Any]:
    resolved_root = root.resolve()
    metadata_items = scan_directory(resolved_root, max_depth=max_depth)
    file_items = [item for item in metadata_items if not item.is_dir]

    duplicate_groups = find_exact_duplicates(metadata_items)
    duplicate_review_plan = build_duplicate_review_plan(
        duplicate_groups,
        resolved_root,
    )
    review_candidates = detect_review_candidates(metadata_items)
    review_candidate_plan = build_review_candidate_plan(
        review_candidates,
        resolved_root,
    )
    project_groups = find_project_groups(metadata_items)
    organization_suggestions = build_organization_suggestions(
        project_groups,
        resolved_root,
    )

    warnings: list[str] = []
    refinement_status = "not_requested"
    refined_suggestions: list[OrganizationSuggestion] = []

    if refine_groups:
        refinement_status = "completed"
        if llm_client is None:
            refinement_status = "failed"
            warnings.append("LLM refinement requested but no client was provided.")
        else:
            try:
                refinements = refine_project_groups_with_ollama(
                    project_groups,
                    llm_client,
                )
                refined_suggestions = [
                    build_refined_organization_suggestion(
                        group,
                        refinement,
                        resolved_root,
                    )
                    for group, refinement in zip(project_groups, refinements)
                ]
            except (RuntimeError, ValueError) as error:
                refinement_status = "failed"
                warnings.append(f"LLM refinement failed: {error}")

    review_candidate_counts_by_category: dict[str, int] = {}
    for candidate in review_candidates:
        review_candidate_counts_by_category[candidate.category] = (
            review_candidate_counts_by_category.get(candidate.category, 0) + 1
        )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scan_root": ".",
        "summary": {
            "file_count": len(file_items),
            "total_bytes": sum(item.size_bytes for item in file_items),
            "duplicate_group_count": len(duplicate_groups),
            "duplicate_candidate_count": len(duplicate_review_plan),
            "review_candidate_count": len(review_candidates),
            "review_candidate_counts_by_category": dict(
                sorted(review_candidate_counts_by_category.items())
            ),
            "project_group_count": len(project_groups),
            "organization_suggestion_count": sum(
                len(suggestion.plan_items)
                for suggestion in organization_suggestions
            ),
            "refinement_status": refinement_status,
        },
        "duplicates": [
            _duplicate_group_to_report(group)
            for group in duplicate_groups
        ],
        "duplicate_review_plan": [
            _plan_item_to_report(item, resolved_root)
            for item in duplicate_review_plan
        ],
        "review_candidates": [
            _review_candidate_to_report(candidate)
            for candidate in review_candidates
        ],
        "review_candidate_plan": [
            _plan_item_to_report(item, resolved_root)
            for item in review_candidate_plan
        ],
        "project_groups": [
            _project_group_to_report(group)
            for group in project_groups
        ],
        "organization_suggestions": [
            _organization_suggestion_to_report(suggestion, resolved_root)
            for suggestion in organization_suggestions
        ],
        "refined_organization_suggestions": [
            _organization_suggestion_to_report(suggestion, resolved_root)
            for suggestion in refined_suggestions
        ],
        "warnings": warnings,
    }


def write_report(
    report: dict[str, Any],
    root: Path,
    output_path: Path | None = None,
) -> Path:
    resolved_root = root.resolve()
    if output_path is None:
        destination = default_report_path(resolved_root)
    elif output_path.is_absolute():
        destination = output_path
    else:
        destination = resolved_root / output_path
    resolved_destination = validate_report_output_path(destination, resolved_root)

    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    with resolved_destination.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2, sort_keys=True)
        file.write("\n")
    return resolved_destination


def default_report_path(root: Path) -> Path:
    reports_dir = root / "AI_Review" / "reports"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = reports_dir / f"{timestamp}_report.json"
    counter = 1
    while os.path.lexists(candidate):
        candidate = reports_dir / f"{timestamp}_{counter}_report.json"
        counter += 1
    return candidate


def validate_report_output_path(path: Path, root: Path) -> Path:
    if os.path.lexists(path):
        raise ValueError(f"report output already exists: {path}")

    resolved_path = path.resolve(strict=False)
    validate_under_root(resolved_path, root)

    existing_parent = _nearest_existing_parent(path.parent)
    resolved_parent = existing_parent.resolve()
    validate_under_root(resolved_parent, root)
    if not existing_parent.is_dir():
        raise ValueError(f"report output parent is not a directory: {existing_parent}")
    return resolved_path


_default_report_path = default_report_path
_validate_report_output_path = validate_report_output_path


def _nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current


def _duplicate_group_to_report(group: DuplicateGroup) -> dict[str, Any]:
    return {
        "sha256": group.sha256,
        "size_bytes": group.size_bytes,
        "files": [
            file.relative_path.as_posix()
            for file in group.files
        ],
    }


def _review_candidate_to_report(candidate: ReviewCandidate) -> dict[str, Any]:
    return {
        "path": candidate.file.relative_path.as_posix(),
        "category": candidate.category,
        "reason": candidate.reason,
        "confidence": candidate.confidence,
    }


def _project_group_to_report(group: ProjectGroup) -> dict[str, Any]:
    return {
        "group_name": group.group_name,
        "reason": group.reason,
        "confidence": group.confidence,
        "files": [
            file.relative_path.as_posix()
            for file in group.files
        ],
    }


def _organization_suggestion_to_report(
    suggestion: OrganizationSuggestion,
    root: Path,
) -> dict[str, Any]:
    return {
        "group_name": suggestion.group.group_name,
        "suggested_root": _relative_path(suggestion.suggested_root, root),
        "plan_items": [
            _plan_item_to_report(item, root)
            for item in suggestion.plan_items
        ],
    }


def _plan_item_to_report(item: MovePlanItem, root: Path) -> dict[str, Any]:
    return {
        "source": _relative_path(item.source, root),
        "destination": _relative_path(item.destination, root),
        "reason": item.reason,
        "confidence": item.confidence,
        "operation": item.operation,
        "overwrite_risk": item.overwrite_risk,
    }


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
