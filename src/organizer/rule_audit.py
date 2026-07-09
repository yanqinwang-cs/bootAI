from __future__ import annotations

from pathlib import Path
from typing import Any

from organizer.grouping import (
    ANCHOR_DECISION_IGNORED,
    ANCHOR_DECISION_NEEDS_DECISION,
    ANCHOR_DECISION_SUGGESTED,
    GROUP_EVIDENCE_LOCKED_ANCHOR,
    AnchorDecision,
    analyze_anchor_decisions,
    find_project_groups,
)
from organizer.models import FileMetadata, ProjectGroup, RuleAudit, RuleEffect
from organizer.organization_rules import (
    ORGANIZATION_RULES_RELATIVE_PATH,
    OrganizationRules,
    OrganizationRulesLoadResult,
    default_organization_rules,
    normalize_anchor,
)


def build_rule_audit(
    files: list[FileMetadata],
    root: Path,
    organization_rules: OrganizationRulesLoadResult,
) -> RuleAudit:
    rules_path = _rules_path_for_report(organization_rules, root)
    if organization_rules.status not in {"loaded", "loaded_with_warnings"}:
        warnings = ["No organization rules file found. Rule-aware audit was skipped."]
        if organization_rules.source_path is not None:
            warnings = [
                "Organization rules file was invalid or unloaded. Rule-aware audit was skipped."
            ]
        warnings.extend(organization_rules.warnings)
        return RuleAudit(
            rules_loaded=False,
            rules_path=rules_path,
            locked_anchors=(),
            ignored_terms=(),
            anchor_aliases={},
            preferred_granularities=(),
            before_after_counts={},
            rule_effects=(),
            warnings=tuple(warnings),
        )

    explicit_rules = _explicit_rule_values(organization_rules)
    before_rules = default_organization_rules()
    after_rules = organization_rules.rules
    before_decisions = analyze_anchor_decisions(files, rules=before_rules)
    after_decisions = analyze_anchor_decisions(files, rules=after_rules)
    before_groups = find_project_groups(files, rules=before_rules)
    after_groups = find_project_groups(files, rules=after_rules)
    before_counts = _counts(before_decisions, before_groups)
    after_counts = _counts(after_decisions, after_groups)
    before_after_counts = {
        "needs_decision_before": before_counts["needs_decision"],
        "needs_decision_after": after_counts["needs_decision"],
        "suggested_groups_before": before_counts["suggested_groups"],
        "suggested_groups_after": after_counts["suggested_groups"],
        "ignored_terms_before": before_counts["ignored_terms"],
        "ignored_terms_after": after_counts["ignored_terms"],
        "organization_suggestions_before": before_counts["organization_suggestions"],
        "organization_suggestions_after": after_counts["organization_suggestions"],
    }
    effects = _rule_effects(
        explicit_rules,
        before_decisions,
        after_decisions,
    )
    warnings = list(organization_rules.warnings)
    warnings.extend(effect.warning for effect in effects if effect.warning)
    warnings.extend(_expansion_warnings(before_after_counts))

    return RuleAudit(
        rules_loaded=True,
        rules_path=rules_path,
        locked_anchors=tuple(explicit_rules["locked_anchors"]),
        ignored_terms=tuple(explicit_rules["ignored_terms"]),
        anchor_aliases=dict(explicit_rules["anchor_aliases"]),
        preferred_granularities=tuple(explicit_rules["preferred_granularities"]),
        before_after_counts=before_after_counts,
        rule_effects=tuple(effects),
        warnings=tuple(warnings),
    )


def rule_audit_to_report(audit: RuleAudit) -> dict[str, Any]:
    return {
        "rules_loaded": audit.rules_loaded,
        "rules_path": audit.rules_path,
        "locked_anchors": list(audit.locked_anchors),
        "ignored_terms": list(audit.ignored_terms),
        "anchor_aliases": dict(sorted(audit.anchor_aliases.items())),
        "preferred_granularities": list(audit.preferred_granularities),
        "before_after_counts": dict(sorted(audit.before_after_counts.items())),
        "rule_effects": [_rule_effect_to_report(effect) for effect in audit.rule_effects],
        "warnings": list(audit.warnings),
    }


def _rule_effect_to_report(effect: RuleEffect) -> dict[str, Any]:
    return {
        "rule_type": effect.rule_type,
        "value": effect.value,
        "effect": effect.effect,
        "matched_file_count": effect.matched_file_count,
        "affected_anchors": list(effect.affected_anchors),
        "before_decision": effect.before_decision,
        "after_decision": effect.after_decision,
        "risk_level": effect.risk_level,
        "warning": effect.warning,
    }


def _explicit_rule_values(load_result: OrganizationRulesLoadResult) -> dict[str, object]:
    data = load_result.raw_data or {}
    return {
        "locked_anchors": tuple(sorted(_string_list(data.get("locked_anchors", [])))),
        "ignored_terms": tuple(sorted(_string_list(data.get("ignored_terms", [])))),
        "anchor_aliases": dict(sorted(_string_map(data.get("anchor_aliases", {})).items())),
        "preferred_granularities": tuple(sorted(_string_list(data.get("preferred_granularities", [])))),
    }


def _rule_effects(
    explicit_rules: dict[str, object],
    before_decisions: list[AnchorDecision],
    after_decisions: list[AnchorDecision],
) -> list[RuleEffect]:
    before_by_anchor = _decisions_by_anchor(before_decisions)
    after_by_anchor = _decisions_by_anchor(after_decisions)
    effects: list[RuleEffect] = []

    for anchor in explicit_rules["locked_anchors"]:
        if not isinstance(anchor, str):
            continue
        before = before_by_anchor.get(normalize_anchor(anchor))
        after = after_by_anchor.get(normalize_anchor(anchor))
        matched = _matched_file_count(before, after)
        risk, warning = _risk_for_locked_anchor(anchor, matched)
        effects.append(
            RuleEffect(
                rule_type="locked_anchor",
                value=anchor,
                effect="Locked anchor is treated as an explicit organization preference in reports.",
                matched_file_count=matched,
                affected_anchors=_affected_anchors(before, after, anchor),
                before_decision=before.decision if before is not None else None,
                after_decision=_after_decision_for_locked_anchor(after),
                risk_level=risk,
                warning=warning,
            )
        )

    for term in explicit_rules["ignored_terms"]:
        if not isinstance(term, str):
            continue
        before = before_by_anchor.get(normalize_anchor(term))
        after = after_by_anchor.get(normalize_anchor(term))
        matched = _matched_file_count(before, after)
        risk, warning = _risk_for_ignored_term(term, matched)
        effects.append(
            RuleEffect(
                rule_type="ignored_term",
                value=term,
                effect="Ignored term suppressed matching anchors in rule-aware output.",
                matched_file_count=matched,
                affected_anchors=_affected_anchors(before, after, term),
                before_decision=before.decision if before is not None else None,
                after_decision=after.decision if after is not None else "ignored_term_loaded",
                risk_level=risk,
                warning=warning,
            )
        )

    aliases = explicit_rules["anchor_aliases"]
    if isinstance(aliases, dict):
        for alias, canonical in aliases.items():
            before = before_by_anchor.get(normalize_anchor(str(alias)))
            after = after_by_anchor.get(normalize_anchor(str(canonical)))
            matched = _matched_file_count(before, after)
            risk, warning = _risk_for_alias(str(alias), matched)
            effects.append(
                RuleEffect(
                    rule_type="anchor_alias",
                    value={"alias": alias, "canonical": canonical},
                    effect="Alias maps matching anchors to a canonical anchor in rule-aware output.",
                    matched_file_count=matched,
                    affected_anchors=_affected_anchors(before, after, str(alias), str(canonical)),
                    before_decision=before.decision if before is not None else None,
                    after_decision=after.decision if after is not None else "alias_loaded",
                    risk_level=risk,
                    warning=warning,
                )
            )

    for granularity in explicit_rules["preferred_granularities"]:
        if not isinstance(granularity, str):
            continue
        effects.append(
            RuleEffect(
                rule_type="preferred_granularity",
                value=granularity,
                effect=(
                    "Preferred granularity is loaded as advisory metadata. "
                    "It does not change organization behavior in this stage."
                ),
                risk_level="none",
            )
        )

    return sorted(
        effects,
        key=lambda effect: (effect.rule_type, str(effect.value)),
    )


def _counts(
    decisions: list[AnchorDecision],
    groups: list[ProjectGroup],
) -> dict[str, int]:
    return {
        "needs_decision": sum(1 for item in decisions if item.decision == ANCHOR_DECISION_NEEDS_DECISION),
        "suggested_groups": sum(1 for item in decisions if item.decision == ANCHOR_DECISION_SUGGESTED),
        "ignored_terms": sum(1 for item in decisions if item.decision == ANCHOR_DECISION_IGNORED),
        "organization_suggestions": sum(len(group.files) for group in groups),
    }


def _expansion_warnings(counts: dict[str, int]) -> list[str]:
    warnings: list[str] = []
    if _expanded(counts["suggested_groups_before"], counts["suggested_groups_after"]):
        warnings.append(
            "Rule-aware suggested groups increased from "
            f"{counts['suggested_groups_before']} to {counts['suggested_groups_after']}. "
            "Review rules before approving any movement."
        )
    if _expanded(
        counts["organization_suggestions_before"],
        counts["organization_suggestions_after"],
    ):
        warnings.append(
            "Rule-aware organization suggestions increased from "
            f"{counts['organization_suggestions_before']} to {counts['organization_suggestions_after']}. "
            "Review rules before approving any movement."
        )
    return warnings


def _expanded(before: int, after: int) -> bool:
    return after > before * 2 and after - before >= 25


def _decisions_by_anchor(decisions: list[AnchorDecision]) -> dict[str, AnchorDecision]:
    return {
        normalize_anchor(decision.anchor): decision
        for decision in decisions
    }


def _matched_file_count(
    before: AnchorDecision | None,
    after: AnchorDecision | None,
) -> int:
    if after is not None:
        return after.file_count
    if before is not None:
        return before.file_count
    return 0


def _affected_anchors(
    *items: AnchorDecision | str | None,
) -> tuple[str, ...]:
    anchors: set[str] = set()
    for item in items:
        if isinstance(item, AnchorDecision):
            anchors.add(item.anchor)
        elif isinstance(item, str) and item:
            anchors.add(item)
    return tuple(sorted(anchors))


def _after_decision_for_locked_anchor(after: AnchorDecision | None) -> str:
    if after is None:
        return "locked_anchor_loaded"
    if after.evidence == GROUP_EVIDENCE_LOCKED_ANCHOR:
        return "locked_anchor"
    return after.decision


def _risk_for_locked_anchor(anchor: str, matched_file_count: int) -> tuple[str, str]:
    risk = _risk_level(matched_file_count)
    if matched_file_count == 0:
        return (
            "low",
            f"Locked anchor {anchor} matched no eligible files in this report.",
        )
    if risk == "high":
        return (
            risk,
            f"Locked anchor {anchor} matched {matched_file_count} files. "
            "Review generated organization suggestions before applying movement.",
        )
    return risk, ""


def _risk_for_ignored_term(term: str, matched_file_count: int) -> tuple[str, str]:
    risk = _risk_level(matched_file_count)
    if risk == "high":
        return (
            risk,
            f"Ignored term {term} matched {matched_file_count} files. "
            "Review ignored anchors before relying on this rule.",
        )
    return risk, ""


def _risk_for_alias(alias: str, matched_file_count: int) -> tuple[str, str]:
    risk = _risk_level(matched_file_count)
    if risk == "high":
        return (
            risk,
            f"Alias {alias} matched {matched_file_count} files. "
            "Review alias effects before approving any movement.",
        )
    return risk, ""


def _risk_level(matched_file_count: int) -> str:
    if matched_file_count <= 10:
        return "low"
    if matched_file_count <= 50:
        return "medium"
    return "high"


def _rules_path_for_report(
    load_result: OrganizationRulesLoadResult,
    root: Path,
) -> str | None:
    if load_result.source_path is None:
        return None
    try:
        return load_result.source_path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return ORGANIZATION_RULES_RELATIVE_PATH.as_posix()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }
