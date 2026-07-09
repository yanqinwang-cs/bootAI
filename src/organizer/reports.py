from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from organizer.duplicates import find_exact_duplicates
from organizer.grouping import (
    ANCHOR_DECISION_IGNORED,
    ANCHOR_DECISION_NEEDS_DECISION,
    ANCHOR_DECISION_SUGGESTED,
    AnchorDecision,
    analyze_anchor_decisions,
    build_organization_suggestions,
    find_project_groups,
)
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
from organizer.organization_rules import OrganizationRulesLoadResult, load_organization_rules
from organizer.pattern_inference import (
    InferredRuleCandidate,
    OrganizationPattern,
    PatternInferenceResult,
    infer_organization_patterns,
    pattern_evidence_for_anchor,
    pattern_priority_for_anchor,
)
from organizer.planner import build_duplicate_review_plan
from organizer.review import build_review_candidate_plan, detect_review_candidates
from organizer.rule_review import rule_candidates_from_inferred
from organizer.safety import validate_under_root
from organizer.scanner import scan_directory
from organizer.scope import is_actionable_plan_eligible

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
    organization_rules = load_organization_rules(resolved_root)

    duplicate_groups = find_exact_duplicates(metadata_items)
    duplicate_review_plan = build_duplicate_review_plan(
        duplicate_groups,
        resolved_root,
        all_metadata=metadata_items,
    )
    review_candidates = detect_review_candidates(metadata_items)
    review_candidate_plan = build_review_candidate_plan(
        review_candidates,
        resolved_root,
    )
    anchor_decisions = analyze_anchor_decisions(
        metadata_items,
        rules=organization_rules.rules,
    )
    pattern_inference = infer_organization_patterns(
        metadata_items,
        anchor_decisions,
    )
    project_groups = find_project_groups(
        metadata_items,
        rules=organization_rules.rules,
    )
    organization_suggestions = build_organization_suggestions(
        project_groups,
        resolved_root,
    )

    warnings: list[str] = []
    warnings.extend(organization_rules.warnings)
    protected_duplicate_candidate_count = _protected_duplicate_candidate_count(
        duplicate_groups,
        metadata_items,
    )
    if protected_duplicate_candidate_count:
        warnings.append(
            f"{protected_duplicate_candidate_count} exact duplicate file(s) are in "
            "protected, generated, or project-output contexts and were not included "
            "as actionable duplicate review plan candidates."
        )
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
    organization_suggestion_count = sum(
        len(suggestion.plan_items)
        for suggestion in organization_suggestions
    )
    if _organization_suggestions_are_unusually_broad(
        organization_suggestion_count,
        len(file_items),
    ):
        warnings.append(
            "Organization suggestions are unusually broad. Consider using --max-depth "
            "or narrowing the organization scope before applying reviewed moves."
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
            "organization_suggestion_count": organization_suggestion_count,
            "suggested_anchor_count": _anchor_decision_count(
                anchor_decisions,
                ANCHOR_DECISION_SUGGESTED,
            ),
            "needs_decision_anchor_count": _anchor_decision_count(
                anchor_decisions,
                ANCHOR_DECISION_NEEDS_DECISION,
            ),
            "ignored_anchor_count": _anchor_decision_count(
                anchor_decisions,
                ANCHOR_DECISION_IGNORED,
            ),
            "organization_pattern_count": len(pattern_inference.patterns),
            "inferred_rule_candidate_count": len(pattern_inference.rule_candidates),
            "refinement_status": refinement_status,
        },
        "organization_rules": _organization_rules_to_report(organization_rules, resolved_root),
        "anchor_decisions": _anchor_decisions_to_report(
            anchor_decisions,
            pattern_inference,
        ),
        "organization_pattern_inference": _pattern_inference_to_report(pattern_inference),
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


def _organization_rules_to_report(
    load_result: OrganizationRulesLoadResult,
    root: Path,
) -> dict[str, Any]:
    source_path = None
    if load_result.source_path is not None:
        source_path = load_result.source_path.relative_to(root).as_posix()
    return {
        "status": load_result.status,
        "path": source_path,
        "message": load_result.message,
        "locked_anchors": sorted(
            load_result.rules.anchor_display_names.get(anchor, anchor)
            for anchor in load_result.rules.locked_anchors
        ),
        "ignored_terms": sorted(load_result.rules.ignored_terms),
        "anchor_aliases": dict(sorted(load_result.rules.anchor_aliases.items())),
    }


def _anchor_decisions_to_report(
    anchor_decisions: list[AnchorDecision],
    pattern_inference: PatternInferenceResult | None = None,
) -> dict[str, list[dict[str, Any]]]:
    needs_decision_items = [
        decision
        for decision in anchor_decisions
        if decision.decision == ANCHOR_DECISION_NEEDS_DECISION
    ]
    if pattern_inference is not None:
        needs_decision_items = sorted(
            needs_decision_items,
            key=lambda decision: (
                _pattern_priority_rank(pattern_priority_for_anchor(decision.anchor, pattern_inference)),
                -decision.file_count,
                decision.anchor,
            ),
        )
    return {
        "suggested_groups": [
            _anchor_decision_to_report(decision, pattern_inference)
            for decision in anchor_decisions
            if decision.decision == ANCHOR_DECISION_SUGGESTED
        ],
        "needs_decision": [
            _anchor_decision_to_report(decision, pattern_inference)
            for decision in needs_decision_items
        ],
        "ignored_terms": [
            _anchor_decision_to_report(decision, pattern_inference)
            for decision in anchor_decisions
            if decision.decision == ANCHOR_DECISION_IGNORED
        ],
    }


def _anchor_decision_to_report(
    decision: AnchorDecision,
    pattern_inference: PatternInferenceResult | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "anchor": decision.anchor,
        "decision": decision.decision,
        "reason": decision.reason,
        "evidence": decision.evidence,
        "file_count": decision.file_count,
        "examples": decision.examples,
    }
    if pattern_inference is not None and decision.decision == ANCHOR_DECISION_NEEDS_DECISION:
        evidence = pattern_evidence_for_anchor(decision.anchor, pattern_inference)
        if evidence is not None:
            item["pattern_evidence"] = evidence
    return item


def _pattern_priority_rank(priority: str) -> int:
    return {
        "high": 0,
        "medium": 1,
        "low": 2,
        "none": 3,
    }.get(priority, 99)


def _pattern_inference_to_report(
    inference: PatternInferenceResult,
) -> dict[str, list[dict[str, Any]]]:
    rule_candidates = rule_candidates_from_inferred(inference.rule_candidates)
    return {
        "patterns": [
            _organization_pattern_to_report(pattern)
            for pattern in inference.patterns
        ],
        "rule_candidates": [
            _inferred_rule_candidate_to_report(candidate)
            for candidate in rule_candidates
        ],
    }


def _organization_pattern_to_report(pattern: OrganizationPattern) -> dict[str, Any]:
    return {
        "pattern_type": pattern.pattern_type,
        "confidence": pattern.confidence,
        "reason": pattern.reason,
        "examples": list(pattern.examples),
        "affected_anchors": list(pattern.affected_anchors),
        "supported_anchors": list(pattern.supported_anchors),
    }


def _inferred_rule_candidate_to_report(
    candidate: Any,
) -> dict[str, Any]:
    return {
        "candidate_id": getattr(candidate, "candidate_id", ""),
        "rule_type": candidate.rule_type,
        "value": candidate.value,
        "confidence": candidate.confidence,
        "reason": candidate.reason,
        "evidence_paths": list(candidate.evidence_paths),
        "suggested_action": getattr(candidate, "suggested_action", "review"),
    }


def _anchor_decision_count(
    anchor_decisions: list[AnchorDecision],
    decision: str,
) -> int:
    return sum(1 for item in anchor_decisions if item.decision == decision)


def _organization_suggestions_are_unusually_broad(
    organization_suggestion_count: int,
    file_count: int,
) -> bool:
    if organization_suggestion_count > 1000:
        return True
    return file_count > 0 and organization_suggestion_count / file_count > 0.5


def _protected_duplicate_candidate_count(
    duplicate_groups: list[DuplicateGroup],
    metadata_items: list[FileMetadata],
) -> int:
    return sum(
        1
        for group in duplicate_groups
        for metadata in group.files
        if not is_actionable_plan_eligible(metadata, metadata_items)
    )


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
