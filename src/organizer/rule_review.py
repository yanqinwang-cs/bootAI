from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable

from organizer.models import RuleCandidate, RuleDecision, RuleReviewResult
from organizer.organization_rules import (
    ORGANIZATION_RULES_RELATIVE_PATH,
    ORGANIZATION_RULES_VERSION,
    normalize_anchor,
)
from organizer.pattern_inference import (
    RULE_ALIAS_CANDIDATE,
    RULE_IGNORE_TERM_CANDIDATE,
    RULE_LOCK_ANCHOR_CANDIDATE,
    RULE_PREFERRED_GRANULARITY_CANDIDATE,
    InferredRuleCandidate,
)
from organizer.safety import validate_under_root

RULE_REVIEW_SCHEMA_VERSION = 1
RULE_REVIEW_DIR = Path("AI_Review") / "rules"
DEFAULT_RULE_CANDIDATES_PATH = RULE_REVIEW_DIR / "organization_rule_candidates.json"
DEFAULT_RULE_APPLY_RESULT_PATH = RULE_REVIEW_DIR / "organization_rule_apply_result.json"
RULE_REVIEW_SOURCE = "bootAI Stage 10.6 organization rule candidates"
RULE_REVIEW_INSTRUCTIONS = (
    "Review each candidate. Set decision to accept, reject, ignore_candidate, "
    "or undecided. Applying accepted decisions requires a separate explicit "
    "confirmation step."
)

DECISION_ACCEPT = "accept"
DECISION_REJECT = "reject"
DECISION_IGNORE_CANDIDATE = "ignore_candidate"
DECISION_UNDECIDED = "undecided"
ALLOWED_DECISIONS = {
    DECISION_ACCEPT,
    DECISION_REJECT,
    DECISION_IGNORE_CANDIDATE,
    DECISION_UNDECIDED,
}
ALLOWED_RULE_TYPES = {
    RULE_LOCK_ANCHOR_CANDIDATE,
    RULE_IGNORE_TERM_CANDIDATE,
    RULE_ALIAS_CANDIDATE,
    RULE_PREFERRED_GRANULARITY_CANDIDATE,
}
SUPPORTED_RULE_CONFIG_KEYS = {
    "version",
    "locked_anchors",
    "ignored_terms",
    "anchor_aliases",
    "preferred_granularities",
}


def rule_candidates_from_inferred(
    inferred_candidates: Iterable[InferredRuleCandidate],
) -> list[RuleCandidate]:
    candidates: list[RuleCandidate] = []
    used_ids: set[str] = set()
    for inferred in sorted(
        inferred_candidates,
        key=lambda item: (-item.confidence, item.rule_type, item.value),
    ):
        value: str | dict[str, str] = inferred.value
        candidate_id = _unique_candidate_id(inferred.rule_type, value, used_ids)
        used_ids.add(candidate_id)
        candidates.append(
            RuleCandidate(
                candidate_id=candidate_id,
                rule_type=inferred.rule_type,
                value=value,
                confidence=inferred.confidence,
                reason=inferred.reason,
                evidence_paths=tuple(sorted(inferred.evidence_paths)),
            )
        )
    return candidates


def rule_candidates_from_report(report: dict[str, Any]) -> list[RuleCandidate]:
    inference = report.get("organization_pattern_inference")
    if not isinstance(inference, dict):
        return []
    raw_candidates = inference.get("rule_candidates")
    if not isinstance(raw_candidates, list):
        return []

    inferred: list[InferredRuleCandidate] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        rule_type = raw.get("rule_type")
        value = raw.get("value")
        confidence = raw.get("confidence")
        reason = raw.get("reason")
        evidence_paths = raw.get("evidence_paths", [])
        if (
            isinstance(rule_type, str)
            and isinstance(value, str)
            and isinstance(confidence, int)
            and isinstance(reason, str)
            and isinstance(evidence_paths, list)
            and all(isinstance(path, str) for path in evidence_paths)
        ):
            inferred.append(
                InferredRuleCandidate(
                    rule_type=rule_type,
                    value=value,
                    confidence=confidence,
                    reason=reason,
                    evidence_paths=tuple(evidence_paths),
                )
            )
    return rule_candidates_from_inferred(inferred)


def export_rule_candidates(
    candidates: list[RuleCandidate],
    root: Path,
    output_path: Path | None = None,
) -> Path:
    resolved_root = root.resolve()
    if output_path is None:
        destination = _collision_safe_path(resolved_root / DEFAULT_RULE_CANDIDATES_PATH)
    else:
        destination = _resolve_user_path(output_path, resolved_root)
        if os.path.lexists(destination):
            raise ValueError(f"rule candidate output already exists: {output_path}")
    resolved_destination = _validate_new_output_path(destination, resolved_root)
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "schema_version": RULE_REVIEW_SCHEMA_VERSION,
        "source": RULE_REVIEW_SOURCE,
        "instructions": RULE_REVIEW_INSTRUCTIONS,
        "candidates": [
            _candidate_to_review_file_item(candidate)
            for candidate in sorted(candidates, key=lambda item: item.candidate_id)
        ],
    }
    with resolved_destination.open("x", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)
        file.write("\n")
    return resolved_destination


def load_reviewed_rule_file(path: Path, root: Path) -> tuple[dict[str, RuleCandidate], dict[str, RuleDecision]]:
    resolved_path = _validate_existing_file_path(path, root.resolve())
    try:
        with resolved_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"reviewed rule decision JSON is invalid: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("reviewed rule decision file must contain a JSON object")
    if data.get("schema_version") != RULE_REVIEW_SCHEMA_VERSION:
        raise ValueError("reviewed rule decision file schema_version must be 1")
    raw_candidates = data.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("reviewed rule decision file must contain a candidates list")

    candidates: dict[str, RuleCandidate] = {}
    decisions: dict[str, RuleDecision] = {}
    for index, raw_candidate in enumerate(raw_candidates, start=1):
        candidate, decision = _review_file_item_to_candidate(raw_candidate, index)
        if candidate.candidate_id in candidates:
            raise ValueError(f"duplicate candidate_id: {candidate.candidate_id}")
        candidates[candidate.candidate_id] = candidate
        decisions[candidate.candidate_id] = decision
    return candidates, decisions


def summarize_rule_decisions(decisions: Iterable[RuleDecision]) -> RuleReviewResult:
    accepted: list[RuleDecision] = []
    rejected: list[RuleDecision] = []
    ignored: list[RuleDecision] = []
    undecided: list[RuleDecision] = []
    for decision in decisions:
        if decision.decision == DECISION_ACCEPT:
            accepted.append(decision)
        elif decision.decision == DECISION_REJECT:
            rejected.append(decision)
        elif decision.decision == DECISION_IGNORE_CANDIDATE:
            ignored.append(decision)
        else:
            undecided.append(decision)
    return RuleReviewResult(
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        ignored=tuple(ignored),
        undecided=tuple(undecided),
        warnings=(),
    )


def apply_rule_decisions(reviewed_path: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    candidates, decisions = load_reviewed_rule_file(reviewed_path, resolved_root)
    rules_path = validate_under_root(resolved_root / ORGANIZATION_RULES_RELATIVE_PATH, resolved_root)
    existing_rules = _load_existing_rules_data(rules_path)
    merged_rules, result = _merge_rule_decisions(existing_rules, candidates, decisions)

    rules_path.parent.mkdir(parents=True, exist_ok=True)
    if result["applied"]:
        _write_json_atomic(rules_path, merged_rules)
    result_path = _collision_safe_path(resolved_root / DEFAULT_RULE_APPLY_RESULT_PATH)
    _validate_new_output_path(result_path, resolved_root).parent.mkdir(parents=True, exist_ok=True)
    with result_path.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2, sort_keys=True)
        file.write("\n")
    return result_path


def _candidate_to_review_file_item(candidate: RuleCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "rule_type": candidate.rule_type,
        "value": candidate.value,
        "confidence": candidate.confidence,
        "reason": candidate.reason,
        "evidence_paths": list(candidate.evidence_paths),
        "suggested_action": candidate.suggested_action,
        "decision": DECISION_UNDECIDED,
        "note": "",
    }


def _review_file_item_to_candidate(raw_candidate: object, index: int) -> tuple[RuleCandidate, RuleDecision]:
    if not isinstance(raw_candidate, dict):
        raise ValueError(f"candidates[{index}] must be an object")
    candidate_id = raw_candidate.get("candidate_id")
    rule_type = raw_candidate.get("rule_type")
    value = raw_candidate.get("value")
    confidence = raw_candidate.get("confidence")
    reason = raw_candidate.get("reason")
    evidence_paths = raw_candidate.get("evidence_paths", [])
    suggested_action = raw_candidate.get("suggested_action", "review")
    decision = raw_candidate.get("decision")
    note = raw_candidate.get("note", "")

    if not isinstance(candidate_id, str) or not _valid_candidate_id(candidate_id):
        raise ValueError(f"candidates[{index}] has invalid candidate_id")
    if rule_type not in ALLOWED_RULE_TYPES:
        raise ValueError(f"candidates[{index}] has unknown rule_type")
    _validate_rule_value(rule_type, value, f"candidates[{index}].value")
    if not isinstance(confidence, int) or not 0 <= confidence <= 100:
        raise ValueError(f"candidates[{index}] confidence must be an integer from 0 to 100")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"candidates[{index}] reason must be a non-empty string")
    if not isinstance(evidence_paths, list) or not all(isinstance(path, str) for path in evidence_paths):
        raise ValueError(f"candidates[{index}] evidence_paths must be a list of strings")
    for evidence_path in evidence_paths:
        _validate_relative_evidence_path(evidence_path)
    if not isinstance(suggested_action, str) or not suggested_action.strip():
        raise ValueError(f"candidates[{index}] suggested_action must be a non-empty string")
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"candidates[{index}] has unknown decision")
    if not isinstance(note, str):
        raise ValueError(f"candidates[{index}] note must be a string")

    return (
        RuleCandidate(
            candidate_id=candidate_id,
            rule_type=rule_type,
            value=value,
            confidence=confidence,
            reason=reason,
            evidence_paths=tuple(evidence_paths),
            suggested_action=suggested_action,
        ),
        RuleDecision(candidate_id=candidate_id, decision=decision, note=note),
    )


def _merge_rule_decisions(
    existing_rules: dict[str, Any],
    candidates: dict[str, RuleCandidate],
    decisions: dict[str, RuleDecision],
) -> tuple[dict[str, Any], dict[str, Any]]:
    locked = _list_to_display_map(existing_rules.get("locked_anchors", []), "locked_anchors")
    ignored = _list_to_display_map(existing_rules.get("ignored_terms", []), "ignored_terms")
    aliases = _aliases_to_display_map(existing_rules.get("anchor_aliases", {}))
    granularities = _list_to_display_map(
        existing_rules.get("preferred_granularities", []),
        "preferred_granularities",
    )

    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    warnings: list[str] = []

    for candidate_id in sorted(candidates):
        candidate = candidates[candidate_id]
        decision = decisions[candidate_id]
        if decision.decision != DECISION_ACCEPT:
            skipped.append(
                {
                    "candidate_id": candidate_id,
                    "decision": decision.decision,
                    "reason": "decision was not accept",
                }
            )
            continue

        if candidate.rule_type == RULE_LOCK_ANCHOR_CANDIDATE and isinstance(candidate.value, str):
            locked[normalize_anchor(candidate.value)] = candidate.value.strip()
            applied.append(_applied_item(candidate))
        elif candidate.rule_type == RULE_IGNORE_TERM_CANDIDATE and isinstance(candidate.value, str):
            ignored[normalize_anchor(candidate.value)] = candidate.value.strip()
            applied.append(_applied_item(candidate))
        elif candidate.rule_type == RULE_PREFERRED_GRANULARITY_CANDIDATE and isinstance(candidate.value, str):
            granularities[normalize_anchor(candidate.value)] = candidate.value.strip()
            applied.append(_applied_item(candidate))
        elif candidate.rule_type == RULE_ALIAS_CANDIDATE and isinstance(candidate.value, dict):
            alias = candidate.value["alias"].strip()
            canonical = candidate.value["canonical"].strip()
            normalized_alias = normalize_anchor(alias)
            existing = aliases.get(normalized_alias)
            if existing is not None and normalize_anchor(existing) != normalize_anchor(canonical):
                warning = (
                    f"alias {alias!r} already maps to {existing!r}; "
                    f"candidate {candidate_id} was skipped"
                )
                warnings.append(warning)
                skipped.append(
                    {
                        "candidate_id": candidate_id,
                        "decision": decision.decision,
                        "reason": warning,
                    }
                )
                continue
            aliases[normalized_alias] = canonical
            applied.append(_applied_item(candidate))
        else:
            raise ValueError(f"candidate {candidate_id} has invalid value for {candidate.rule_type}")

    merged = {
        "version": ORGANIZATION_RULES_VERSION,
        "locked_anchors": _sorted_display_values(locked),
        "ignored_terms": _sorted_display_values(ignored),
        "anchor_aliases": {
            alias: aliases[alias]
            for alias in sorted(aliases)
        },
        "preferred_granularities": _sorted_display_values(granularities),
    }
    result = {
        "schema_version": RULE_REVIEW_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "applied": applied,
        "skipped": skipped,
        "warnings": warnings,
    }
    return merged, result


def _load_existing_rules_data(rules_path: Path) -> dict[str, Any]:
    if not os.path.lexists(rules_path):
        return {
            "version": ORGANIZATION_RULES_VERSION,
            "locked_anchors": [],
            "ignored_terms": [],
            "anchor_aliases": {},
            "preferred_granularities": [],
        }
    if not rules_path.is_file():
        raise ValueError(f"organization rules path is not a file: {rules_path}")
    try:
        with rules_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"organization rules JSON is invalid: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("organization rules must be a JSON object")
    unknown = set(data) - SUPPORTED_RULE_CONFIG_KEYS
    if unknown:
        raise ValueError(f"organization rules contain unsupported field(s): {', '.join(sorted(unknown))}")
    if data.get("version") != ORGANIZATION_RULES_VERSION:
        raise ValueError("organization rules version must be 1")
    _list_to_display_map(data.get("locked_anchors", []), "locked_anchors")
    _list_to_display_map(data.get("ignored_terms", []), "ignored_terms")
    _aliases_to_display_map(data.get("anchor_aliases", {}))
    _list_to_display_map(data.get("preferred_granularities", []), "preferred_granularities")
    return data


def _list_to_display_map(value: object, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise ValueError(f"organization rules {field_name} must be a list")
    values: dict[str, str] = {}
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not _valid_rule_string(item):
            raise ValueError(f"organization rules {field_name}[{index}] is invalid")
        values[normalize_anchor(item)] = item.strip()
    return values


def _aliases_to_display_map(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("organization rules anchor_aliases must be an object")
    aliases: dict[str, str] = {}
    for raw_alias, raw_canonical in value.items():
        if (
            not isinstance(raw_alias, str)
            or not isinstance(raw_canonical, str)
            or not _valid_rule_string(raw_alias)
            or not _valid_rule_string(raw_canonical)
        ):
            raise ValueError("organization rules anchor_aliases contains an invalid entry")
        aliases[normalize_anchor(raw_alias)] = raw_canonical.strip()
    return aliases


def _applied_item(candidate: RuleCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "rule_type": candidate.rule_type,
        "value": candidate.value,
    }


def _sorted_display_values(values: dict[str, str]) -> list[str]:
    return [values[key] for key in sorted(values)]


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)
        file.write("\n")
    os.replace(temporary_path, path)


def _unique_candidate_id(
    rule_type: str,
    value: str | dict[str, str],
    used_ids: set[str],
) -> str:
    base = _candidate_id_base(rule_type, value)
    if base not in used_ids:
        return base
    digest = hashlib.sha256(_stable_value_text(rule_type, value).encode("utf-8")).hexdigest()[:8]
    candidate_id = f"{base}-{digest}"
    counter = 2
    while candidate_id in used_ids:
        candidate_id = f"{base}-{digest}-{counter}"
        counter += 1
    return candidate_id


def _candidate_id_base(rule_type: str, value: str | dict[str, str]) -> str:
    if rule_type == RULE_LOCK_ANCHOR_CANDIDATE and isinstance(value, str):
        return f"lock-anchor-{_slug(value)}"
    if rule_type == RULE_IGNORE_TERM_CANDIDATE and isinstance(value, str):
        return f"ignore-term-{_slug(value)}"
    if rule_type == RULE_PREFERRED_GRANULARITY_CANDIDATE and isinstance(value, str):
        return f"preferred-granularity-{_slug(value)}"
    if rule_type == RULE_ALIAS_CANDIDATE and isinstance(value, dict):
        canonical = value.get("canonical", "")
        alias = value.get("alias", "")
        return f"alias-{_slug(str(canonical))}-{_slug(str(alias))}"
    return f"candidate-{_slug(_stable_value_text(rule_type, value))}"


def _stable_value_text(rule_type: str, value: str | dict[str, str]) -> str:
    return json.dumps({"rule_type": rule_type, "value": value}, sort_keys=True)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "value"


def _valid_candidate_id(candidate_id: str) -> bool:
    return (
        bool(candidate_id)
        and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", candidate_id) is not None
        and "/" not in candidate_id
        and "\\" not in candidate_id
        and ".." not in candidate_id
    )


def _validate_rule_value(rule_type: str, value: object, field_name: str) -> None:
    if rule_type in {
        RULE_LOCK_ANCHOR_CANDIDATE,
        RULE_IGNORE_TERM_CANDIDATE,
        RULE_PREFERRED_GRANULARITY_CANDIDATE,
    }:
        if not isinstance(value, str) or not _valid_rule_string(value):
            raise ValueError(f"{field_name} must be a safe non-empty string")
        return
    if rule_type == RULE_ALIAS_CANDIDATE:
        if not isinstance(value, dict):
            raise ValueError(f"{field_name} must be an alias object")
        alias = value.get("alias")
        canonical = value.get("canonical")
        if not isinstance(alias, str) or not _valid_rule_string(alias):
            raise ValueError(f"{field_name}.alias must be a safe non-empty string")
        if not isinstance(canonical, str) or not _valid_rule_string(canonical):
            raise ValueError(f"{field_name}.canonical must be a safe non-empty string")
        return
    raise ValueError(f"unknown rule_type: {rule_type}")


def _valid_rule_string(value: str) -> bool:
    stripped = value.strip()
    return (
        bool(stripped)
        and stripped not in {".", ".."}
        and "\x00" not in stripped
        and "/" not in stripped
        and "\\" not in stripped
        and ".." not in stripped
    )


def _validate_relative_evidence_path(path_text: str) -> None:
    if not path_text or "\x00" in path_text:
        raise ValueError("evidence_paths entries must be non-empty relative paths")
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe evidence path: {path_text}")


def _resolve_user_path(path: Path, root: Path) -> Path:
    return path if path.is_absolute() else root / path


def _validate_existing_file_path(path: Path, root: Path) -> Path:
    candidate = _resolve_user_path(path, root)
    resolved = validate_under_root(candidate, root)
    if not resolved.exists():
        raise ValueError(f"reviewed rule decision file does not exist: {path}")
    if not resolved.is_file():
        raise ValueError(f"reviewed rule decision path is not a file: {path}")
    return resolved


def _validate_new_output_path(path: Path, root: Path) -> Path:
    resolved = validate_under_root(path, root)
    if os.path.lexists(resolved):
        raise ValueError(f"output already exists: {path}")
    existing_parent = resolved.parent
    while not existing_parent.exists():
        if existing_parent.parent == existing_parent:
            break
        existing_parent = existing_parent.parent
    validate_under_root(existing_parent, root)
    if not existing_parent.is_dir():
        raise ValueError(f"output parent is not a directory: {existing_parent}")
    return resolved


def _collision_safe_path(path: Path) -> Path:
    if not os.path.lexists(path):
        return path
    for counter in range(1, 1000):
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not os.path.lexists(candidate):
            return candidate
    raise ValueError(f"could not find unused output path for {path}")
