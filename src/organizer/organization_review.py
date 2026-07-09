from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PureWindowsPath
import re
from typing import Any

from organizer.organization_rules import normalize_anchor
from organizer.reports import validate_report_output_path
from organizer.safety import validate_under_root

ORGANIZATION_REVIEW_SCHEMA_VERSION = 1
ORGANIZATION_REVIEW_SOURCE = "bootAI Stage 10.8 rule-aware organization review"
ORGANIZATION_REVIEW_INSTRUCTIONS = (
    "Review each organization suggestion. Set decision to approve, reject, or "
    "undecided. Applying approved movement requires a later explicit confirmation step."
)
DEFAULT_ORGANIZATION_REVIEW_PATH = (
    Path("AI_Review") / "reviews" / "organization_review.json"
)

DECISION_APPROVE = "approve"
DECISION_REJECT = "reject"
DECISION_UNDECIDED = "undecided"
ALLOWED_DECISIONS = {
    DECISION_APPROVE,
    DECISION_REJECT,
    DECISION_UNDECIDED,
}
ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
NARROW_EVIDENCE = {
    "year_variant_set",
    "numbered_series",
    "question_solution_set",
    "title_variant_set",
}

_TOP_LEVEL_FIELDS = {
    "schema_version",
    "source",
    "generated_at",
    "scan_root",
    "instructions",
    "rules_loaded",
    "rules_path",
    "rule_audit_summary",
    "items",
}
_AUDIT_SUMMARY_FIELDS = {
    "locked_anchors",
    "preferred_granularities",
    "warnings",
}
_ITEM_FIELDS = {
    "review_id",
    "source",
    "destination",
    "anchor",
    "evidence",
    "reason",
    "confidence",
    "risk_level",
    "overwrite_risk",
    "decision",
    "note",
}


def build_organization_review(report: dict[str, Any]) -> dict[str, Any]:
    suggestions = report.get("organization_suggestions")
    if not isinstance(suggestions, list):
        raise ValueError("report organization_suggestions must be a list")

    anchor_decisions = _suggested_anchor_decisions(report)
    locked_counts = _locked_anchor_file_counts(report, anchor_decisions)
    rows: list[dict[str, Any]] = []

    for suggestion_index, suggestion in enumerate(suggestions, start=1):
        if not isinstance(suggestion, dict):
            raise ValueError(
                f"report organization_suggestions[{suggestion_index}] must be an object"
            )
        group_name = suggestion.get("group_name")
        if not isinstance(group_name, str) or not group_name.strip():
            raise ValueError(
                f"report organization_suggestions[{suggestion_index}] has invalid group_name"
            )
        normalized_anchor = normalize_anchor(group_name)
        decision = anchor_decisions.get(normalized_anchor)
        evidence = "deterministic_group"
        if decision is not None:
            raw_evidence = decision.get("evidence")
            if isinstance(raw_evidence, str) and raw_evidence.strip():
                evidence = raw_evidence

        plan_items = suggestion.get("plan_items")
        if not isinstance(plan_items, list):
            raise ValueError(
                f"report organization_suggestions[{suggestion_index}].plan_items "
                "must be a list"
            )
        for plan_index, plan_item in enumerate(plan_items, start=1):
            if not isinstance(plan_item, dict):
                raise ValueError(
                    "report organization_suggestions"
                    f"[{suggestion_index}].plan_items[{plan_index}] must be an object"
                )
            source = plan_item.get("source")
            destination = plan_item.get("destination")
            reason = plan_item.get("reason")
            confidence = plan_item.get("confidence")
            overwrite_risk = plan_item.get("overwrite_risk")
            if not isinstance(source, str):
                raise ValueError("organization suggestion source must be a string")
            if not isinstance(destination, str):
                raise ValueError("organization suggestion destination must be a string")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("organization suggestion reason must be a non-empty string")
            if type(confidence) is not int or not 0 <= confidence <= 100:
                raise ValueError(
                    "organization suggestion confidence must be an integer from 0 to 100"
                )
            if not isinstance(overwrite_risk, bool):
                raise ValueError("organization suggestion overwrite_risk must be a boolean")

            rows.append(
                {
                    "source": source,
                    "destination": destination,
                    "anchor": group_name,
                    "evidence": evidence,
                    "reason": reason,
                    "confidence": confidence,
                    "risk_level": _risk_level(
                        evidence,
                        confidence,
                        overwrite_risk,
                        locked_counts.get(normalized_anchor, 0),
                    ),
                    "overwrite_risk": overwrite_risk,
                    "decision": DECISION_UNDECIDED,
                    "note": "",
                }
            )

    rows.sort(
        key=lambda item: (
            normalize_anchor(str(item["anchor"])),
            str(item["source"]),
            str(item["destination"]),
        )
    )
    items = [
        {"review_id": f"org-{index:06d}", **row}
        for index, row in enumerate(rows, start=1)
    ]

    rule_audit = report.get("rule_audit")
    if not isinstance(rule_audit, dict):
        raise ValueError("report rule_audit must be an object")
    rules_loaded = rule_audit.get("rules_loaded")
    if not isinstance(rules_loaded, bool):
        raise ValueError("report rule_audit.rules_loaded must be a boolean")
    rules_path = rule_audit.get("rules_path")
    if rules_path is not None and not isinstance(rules_path, str):
        raise ValueError("report rule_audit.rules_path must be a string or null")

    warnings = _string_list(rule_audit.get("warnings", []), "rule_audit.warnings")
    warnings.extend(
        _broad_locked_anchor_warnings(locked_counts, anchor_decisions)
    )
    if not items:
        warnings.append("No organization suggestions were available for review.")

    data = {
        "schema_version": ORGANIZATION_REVIEW_SCHEMA_VERSION,
        "source": ORGANIZATION_REVIEW_SOURCE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scan_root": _required_string(report.get("scan_root"), "report scan_root"),
        "instructions": ORGANIZATION_REVIEW_INSTRUCTIONS,
        "rules_loaded": rules_loaded,
        "rules_path": rules_path,
        "rule_audit_summary": {
            "locked_anchors": _string_list(
                rule_audit.get("locked_anchors", []),
                "rule_audit.locked_anchors",
            ),
            "preferred_granularities": _string_list(
                rule_audit.get("preferred_granularities", []),
                "rule_audit.preferred_granularities",
            ),
            "warnings": _deduplicated(warnings),
        },
        "items": items,
    }
    return validate_organization_review_data(data)


def export_organization_review(
    report: dict[str, Any],
    root: Path,
    output_path: Path | None = None,
) -> Path:
    resolved_root = root.resolve()
    if output_path is None:
        destination = _collision_safe_path(
            resolved_root / DEFAULT_ORGANIZATION_REVIEW_PATH
        )
    else:
        destination = output_path if output_path.is_absolute() else resolved_root / output_path
        if os.path.lexists(destination):
            raise ValueError(f"organization review output already exists: {output_path}")

    resolved_destination = validate_report_output_path(destination, resolved_root)
    data = build_organization_review(report)
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    with resolved_destination.open("x", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)
        file.write("\n")
    return resolved_destination


def load_organization_review(path: Path, root: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    candidate = path if path.is_absolute() else resolved_root / path
    resolved_path = validate_under_root(candidate, resolved_root)
    if not resolved_path.exists():
        raise ValueError(f"organization review file does not exist: {path}")
    if not resolved_path.is_file():
        raise ValueError(f"organization review path is not a file: {path}")
    try:
        with resolved_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"organization review JSON is invalid: {error}") from error
    return validate_organization_review_data(data)


def validate_organization_review_data(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("organization review must contain a JSON object")
    _require_exact_fields(data, _TOP_LEVEL_FIELDS, "organization review")
    if data.get("schema_version") != ORGANIZATION_REVIEW_SCHEMA_VERSION:
        raise ValueError("organization review schema_version must be 1")
    if data.get("source") != ORGANIZATION_REVIEW_SOURCE:
        raise ValueError("organization review source is invalid")
    _validate_timestamp(data.get("generated_at"))
    _required_string(data.get("scan_root"), "organization review scan_root")
    _required_string(data.get("instructions"), "organization review instructions")
    if not isinstance(data.get("rules_loaded"), bool):
        raise ValueError("organization review rules_loaded must be a boolean")
    rules_path = data.get("rules_path")
    if rules_path is not None:
        _validate_relative_path(rules_path, "organization review rules_path")

    summary = data.get("rule_audit_summary")
    if not isinstance(summary, dict):
        raise ValueError("organization review rule_audit_summary must be an object")
    _require_exact_fields(summary, _AUDIT_SUMMARY_FIELDS, "rule_audit_summary")
    _string_list(summary.get("locked_anchors"), "rule_audit_summary.locked_anchors")
    _string_list(
        summary.get("preferred_granularities"),
        "rule_audit_summary.preferred_granularities",
    )
    _string_list(summary.get("warnings"), "rule_audit_summary.warnings")

    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("organization review items must be a list")
    review_ids: set[str] = set()
    for index, item in enumerate(items, start=1):
        _validate_review_item(item, index, review_ids)
    return data


def _validate_review_item(
    item: object,
    index: int,
    review_ids: set[str],
) -> None:
    label = f"items[{index}]"
    if not isinstance(item, dict):
        raise ValueError(f"{label} must be an object")
    _require_exact_fields(item, _ITEM_FIELDS, label)
    review_id = item.get("review_id")
    if not isinstance(review_id, str) or re.fullmatch(r"org-\d{6}", review_id) is None:
        raise ValueError(f"{label} has invalid review_id")
    if review_id in review_ids:
        raise ValueError(f"duplicate review_id: {review_id}")
    review_ids.add(review_id)

    _validate_relative_path(item.get("source"), f"{label}.source")
    destination = _validate_relative_path(
        item.get("destination"),
        f"{label}.destination",
    )
    if len(destination.parts) < 2 or destination.parts[0] != "Organized":
        raise ValueError(f"{label}.destination must be under Organized/")
    _validate_anchor(item.get("anchor"), f"{label}.anchor")
    _required_string(item.get("evidence"), f"{label}.evidence")
    _required_string(item.get("reason"), f"{label}.reason")
    confidence = item.get("confidence")
    if type(confidence) is not int or not 0 <= confidence <= 100:
        raise ValueError(f"{label}.confidence must be an integer from 0 to 100")
    if item.get("risk_level") not in ALLOWED_RISK_LEVELS:
        raise ValueError(f"{label}.risk_level is invalid")
    if not isinstance(item.get("overwrite_risk"), bool):
        raise ValueError(f"{label}.overwrite_risk must be a boolean")
    if item.get("decision") not in ALLOWED_DECISIONS:
        raise ValueError(f"{label}.decision is invalid")
    if not isinstance(item.get("note"), str):
        raise ValueError(f"{label}.note must be a string")


def _suggested_anchor_decisions(
    report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    anchor_decisions = report.get("anchor_decisions")
    if not isinstance(anchor_decisions, dict):
        raise ValueError("report anchor_decisions must be an object")
    suggested = anchor_decisions.get("suggested_groups")
    if not isinstance(suggested, list):
        raise ValueError("report anchor_decisions.suggested_groups must be a list")
    decisions: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(suggested, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"report suggested_groups[{index}] must be an object")
        anchor = item.get("anchor")
        if not isinstance(anchor, str) or not anchor.strip():
            raise ValueError(f"report suggested_groups[{index}] has invalid anchor")
        decisions[normalize_anchor(anchor)] = item
    return decisions


def _locked_anchor_file_counts(
    report: dict[str, Any],
    anchor_decisions: dict[str, dict[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for anchor, decision in anchor_decisions.items():
        if decision.get("evidence") != "locked_anchor":
            continue
        file_count = decision.get("file_count")
        if type(file_count) is int and file_count >= 0:
            counts[anchor] = file_count

    rule_audit = report.get("rule_audit")
    if not isinstance(rule_audit, dict):
        return counts
    effects = rule_audit.get("rule_effects", [])
    if not isinstance(effects, list):
        raise ValueError("report rule_audit.rule_effects must be a list")
    for effect in effects:
        if not isinstance(effect, dict) or effect.get("rule_type") != "locked_anchor":
            continue
        matched = effect.get("matched_file_count")
        if type(matched) is not int or matched < 0:
            continue
        anchors: list[str] = []
        value = effect.get("value")
        if isinstance(value, str):
            anchors.append(value)
        affected = effect.get("affected_anchors", [])
        if isinstance(affected, list):
            anchors.extend(anchor for anchor in affected if isinstance(anchor, str))
        for anchor in anchors:
            normalized = normalize_anchor(anchor)
            counts[normalized] = max(counts.get(normalized, 0), matched)
    return counts


def _risk_level(
    evidence: str,
    confidence: int,
    overwrite_risk: bool,
    locked_anchor_file_count: int,
) -> str:
    if overwrite_risk:
        return "high"
    if evidence == "locked_anchor":
        if locked_anchor_file_count > 50:
            return "high"
        if locked_anchor_file_count >= 11:
            return "medium"
        if locked_anchor_file_count >= 1:
            return "low"
        return "medium"
    if evidence in NARROW_EVIDENCE and confidence >= 80:
        return "low"
    return "medium"


def _broad_locked_anchor_warnings(
    counts: dict[str, int],
    anchor_decisions: dict[str, dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    for anchor, count in sorted(counts.items()):
        if count <= 50:
            continue
        decision = anchor_decisions.get(anchor, {})
        display_anchor = decision.get("anchor", anchor)
        warnings.append(
            f"Locked anchor {display_anchor} matched {count} files. Review generated "
            "organization suggestions before applying movement."
        )
    return warnings


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("organization review generated_at must be a timestamp string")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("organization review generated_at must be an ISO timestamp") from error
    if timestamp.tzinfo is None:
        raise ValueError("organization review generated_at must include a timezone")


def _validate_relative_path(value: object, field_name: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError(f"{field_name} must be a safe relative path")
    path = Path(value)
    windows_path = PureWindowsPath(value)
    if (
        path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or value in {".", ".."}
        or ".." in path.parts
    ):
        raise ValueError(f"{field_name} must be a safe relative path")
    return path


def _validate_anchor(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a safe non-empty string")
    stripped = value.strip()
    if (
        not stripped
        or stripped in {".", ".."}
        or "\x00" in stripped
        or "/" in stripped
        or "\\" in stripped
        or ":" in stripped
        or ".." in stripped
    ):
        raise ValueError(f"{field_name} must be a safe non-empty string")


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return list(value)


def _require_exact_fields(
    data: dict[str, Any],
    expected: set[str],
    label: str,
) -> None:
    missing = expected - set(data)
    if missing:
        raise ValueError(f"{label} is missing field(s): {', '.join(sorted(missing))}")
    unknown = set(data) - expected
    if unknown:
        raise ValueError(f"{label} has unsupported field(s): {', '.join(sorted(unknown))}")


def _collision_safe_path(path: Path) -> Path:
    if not os.path.lexists(path):
        return path
    for counter in range(1, 1000):
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not os.path.lexists(candidate):
            return candidate
    raise ValueError(f"could not find unused output path for {path}")


def _deduplicated(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
