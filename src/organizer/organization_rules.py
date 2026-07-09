from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


ORGANIZATION_RULES_VERSION = 1
ORGANIZATION_RULES_RELATIVE_PATH = Path("AI_Review") / "config" / "organization_rules.json"
DEFAULT_IGNORED_TERMS = frozenset(
    {
        "appendix",
        "balanced",
        "chat",
        "copy",
        "data",
        "debug",
        "draft",
        "field",
        "final",
        "full",
        "image",
        "index",
        "instructions",
        "module",
        "modules",
        "new",
        "old",
        "other",
        "output",
        "pasted",
        "report",
        "resource",
        "resources",
        "results",
        "run",
        "summary",
        "untitled",
        "updated",
        "v1",
        "v2",
        "v3",
    }
)


@dataclass(frozen=True)
class OrganizationRules:
    locked_anchors: frozenset[str]
    ignored_terms: frozenset[str]
    anchor_aliases: dict[str, str]
    anchor_display_names: dict[str, str]
    preferred_granularities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class OrganizationRulesLoadResult:
    rules: OrganizationRules
    source_path: Path | None
    status: str
    message: str
    warnings: list[str]
    raw_data: dict[str, Any] | None = None


def default_organization_rules() -> OrganizationRules:
    return OrganizationRules(
        locked_anchors=frozenset(),
        ignored_terms=DEFAULT_IGNORED_TERMS,
        anchor_aliases={},
        anchor_display_names={},
        preferred_granularities=frozenset(),
    )


def load_organization_rules(root: Path) -> OrganizationRulesLoadResult:
    rules_path = root.resolve() / ORGANIZATION_RULES_RELATIVE_PATH
    if not rules_path.exists():
        return OrganizationRulesLoadResult(
            rules=default_organization_rules(),
            source_path=None,
            status="defaults",
            message="No organization rules file found. Using conservative built-in defaults.",
            warnings=[],
        )
    if not rules_path.is_file():
        return OrganizationRulesLoadResult(
            rules=default_organization_rules(),
            source_path=rules_path,
            status="defaults_with_warnings",
            message="Organization rules path is not a file. Using conservative built-in defaults.",
            warnings=[f"Organization rules path is not a file: {ORGANIZATION_RULES_RELATIVE_PATH.as_posix()}"],
        )

    try:
        with rules_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        return OrganizationRulesLoadResult(
            rules=default_organization_rules(),
            source_path=rules_path,
            status="defaults_with_warnings",
            message="Organization rules JSON is invalid. Using conservative built-in defaults.",
            warnings=[f"Organization rules JSON is invalid: {error}"],
        )

    rules, warnings = organization_rules_from_data(data)
    status = "loaded_with_warnings" if warnings else "loaded"
    return OrganizationRulesLoadResult(
        rules=rules,
        source_path=rules_path,
        status=status,
        message=f"Loaded organization rules from {ORGANIZATION_RULES_RELATIVE_PATH.as_posix()}.",
        warnings=warnings,
        raw_data=data,
    )


def organization_rules_from_data(data: object) -> tuple[OrganizationRules, list[str]]:
    warnings: list[str] = []
    if not isinstance(data, dict):
        return (
            default_organization_rules(),
            ["Organization rules must be a JSON object. Using conservative built-in defaults."],
        )
    if data.get("version") != ORGANIZATION_RULES_VERSION:
        return (
            default_organization_rules(),
            ["Organization rules version must be 1. Using conservative built-in defaults."],
        )

    locked, locked_display = _string_list_to_anchor_set(
        data.get("locked_anchors", []),
        "locked_anchors",
        warnings,
    )
    ignored, ignored_display = _string_list_to_anchor_set(
        data.get("ignored_terms", []),
        "ignored_terms",
        warnings,
    )
    ignored = frozenset(set(DEFAULT_IGNORED_TERMS) | set(ignored))

    aliases, alias_display = _aliases_from_data(data.get("anchor_aliases", {}), warnings)
    aliases = _reject_alias_cycles(aliases, warnings)
    aliases = _resolve_alias_chains(aliases, warnings)
    preferred_granularities = _string_list_to_plain_set(
        data.get("preferred_granularities", []),
        "preferred_granularities",
        warnings,
    )

    normalized_ignored = {_resolve_anchor(term, aliases) for term in ignored}
    normalized_locked = {_resolve_anchor(term, aliases) for term in locked}
    alias_targets_to_ignored = {
        alias
        for alias, target in aliases.items()
        if target in normalized_ignored
    }
    if alias_targets_to_ignored:
        for alias in sorted(alias_targets_to_ignored):
            warnings.append(
                f"anchor_aliases entry {alias!r} points to an ignored term and was ignored"
            )
            aliases.pop(alias, None)

    normalized_ignored = {_resolve_anchor(term, aliases) for term in ignored}
    normalized_locked = {_resolve_anchor(term, aliases) for term in locked}
    conflicts = normalized_locked & normalized_ignored
    if conflicts:
        for anchor in sorted(conflicts):
            warnings.append(
                f"locked_anchors entry {anchor!r} is also ignored; ignored term wins"
            )
        normalized_locked -= conflicts

    display_names: dict[str, str] = {}
    for mapping in (locked_display, ignored_display, alias_display):
        for key, display in mapping.items():
            canonical = _resolve_anchor(key, aliases)
            display_names.setdefault(canonical, display)
    for target in aliases.values():
        display_names.setdefault(target, _default_display_name(target))

    return (
        OrganizationRules(
            locked_anchors=frozenset(normalized_locked),
            ignored_terms=frozenset(normalized_ignored),
            anchor_aliases=dict(sorted(aliases.items())),
            anchor_display_names=dict(sorted(display_names.items())),
            preferred_granularities=frozenset(preferred_granularities),
        ),
        warnings,
    )


def organization_rules_to_data(rules: OrganizationRules) -> dict[str, Any]:
    return {
        "version": ORGANIZATION_RULES_VERSION,
        "locked_anchors": sorted(rules.locked_anchors),
        "ignored_terms": sorted(
            term for term in rules.ignored_terms if term not in DEFAULT_IGNORED_TERMS
        ),
        "anchor_aliases": dict(sorted(rules.anchor_aliases.items())),
        "preferred_granularities": sorted(rules.preferred_granularities),
    }


def normalize_anchor(text: str) -> str:
    return text.strip().lower()


def canonical_anchor(anchor: str, rules: OrganizationRules) -> str:
    return _resolve_anchor(normalize_anchor(anchor), rules.anchor_aliases)


def display_anchor(anchor: str, rules: OrganizationRules, fallback: str | None = None) -> str:
    canonical = canonical_anchor(anchor, rules)
    return rules.anchor_display_names.get(canonical, fallback or _default_display_name(canonical))


def _string_list_to_anchor_set(
    value: object,
    field_name: str,
    warnings: list[str],
) -> tuple[frozenset[str], dict[str, str]]:
    if value is None:
        return frozenset(), {}
    if not isinstance(value, list):
        warnings.append(f"{field_name} must be a list; ignoring this section")
        return frozenset(), {}

    anchors: set[str] = set()
    display_names: dict[str, str] = {}
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str):
            warnings.append(f"{field_name}[{index}] must be a string and was ignored")
            continue
        normalized = normalize_anchor(item)
        if not _valid_anchor(normalized):
            warnings.append(f"{field_name}[{index}] is not a valid anchor and was ignored")
            continue
        anchors.add(normalized)
        display_names.setdefault(normalized, item.strip())
    return frozenset(anchors), display_names


def _string_list_to_plain_set(
    value: object,
    field_name: str,
    warnings: list[str],
) -> frozenset[str]:
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        warnings.append(f"{field_name} must be a list; ignoring this section")
        return frozenset()

    items: set[str] = set()
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str):
            warnings.append(f"{field_name}[{index}] must be a string and was ignored")
            continue
        normalized = normalize_anchor(item)
        if not _valid_anchor(normalized):
            warnings.append(f"{field_name}[{index}] is not valid and was ignored")
            continue
        items.add(normalized)
    return frozenset(items)


def _aliases_from_data(value: object, warnings: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    if value is None:
        return {}, {}
    if not isinstance(value, dict):
        warnings.append("anchor_aliases must be an object; ignoring this section")
        return {}, {}

    aliases: dict[str, str] = {}
    display_names: dict[str, str] = {}
    for raw_alias, raw_target in value.items():
        if not isinstance(raw_alias, str) or not isinstance(raw_target, str):
            warnings.append("anchor_aliases entries must map strings to strings and one entry was ignored")
            continue
        alias = normalize_anchor(raw_alias)
        target = normalize_anchor(raw_target)
        if not _valid_anchor(alias) or not _valid_anchor(target):
            warnings.append(f"anchor_aliases entry {raw_alias!r} is invalid and was ignored")
            continue
        if alias == target:
            display_names.setdefault(target, raw_target.strip())
            continue
        aliases[alias] = target
        display_names.setdefault(target, raw_target.strip())
    return aliases, display_names


def _reject_alias_cycles(aliases: dict[str, str], warnings: list[str]) -> dict[str, str]:
    valid = dict(aliases)
    for alias in sorted(aliases):
        seen: set[str] = set()
        current = alias
        while current in aliases:
            if current in seen:
                warnings.append(f"anchor_aliases entry {alias!r} is part of a cycle and was ignored")
                valid.pop(alias, None)
                break
            seen.add(current)
            current = aliases[current]
    return valid


def _resolve_alias_chains(aliases: dict[str, str], warnings: list[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for alias in sorted(aliases):
        target = aliases[alias]
        seen = {alias}
        while target in aliases and target not in seen:
            seen.add(target)
            target = aliases[target]
        if target in seen:
            warnings.append(f"anchor_aliases entry {alias!r} could not be resolved and was ignored")
            continue
        resolved[alias] = target
    return resolved


def _resolve_anchor(anchor: str, aliases: dict[str, str]) -> str:
    current = anchor
    seen: set[str] = set()
    while current in aliases and current not in seen:
        seen.add(current)
        current = aliases[current]
    return current


def _valid_anchor(anchor: str) -> bool:
    return (
        bool(anchor)
        and anchor not in {".", ".."}
        and "\x00" not in anchor
        and "/" not in anchor
        and "\\" not in anchor
    )


def _default_display_name(anchor: str) -> str:
    if anchor.upper() == anchor and any(character.isdigit() for character in anchor):
        return anchor
    if any(character.isdigit() for character in anchor) and any(character.isalpha() for character in anchor):
        return anchor.upper()
    return anchor.replace("_", " ").title().replace(" ", "_")
