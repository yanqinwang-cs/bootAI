import re
from dataclasses import dataclass
from pathlib import Path

from organizer.grouping import (
    ANCHOR_DECISION_NEEDS_DECISION,
    AnchorDecision,
    extract_course_code,
    normalize_token,
)
from organizer.models import FileMetadata
from organizer.scope import is_allowed_organization_file, is_actionable_source_path

PATTERN_COURSE_CODE_FOLDERING = "course_code_foldering"
PATTERN_PROJECT_FOLDERING = "project_foldering"
PATTERN_PERSON_OR_STUDENT_FOLDERING = "person_or_student_foldering"
PATTERN_ROLE_FOLDERING = "role_foldering"
PATTERN_YEAR_FOLDERING = "year_foldering"
PATTERN_FORMAT_FOLDERING = "format_foldering"
PATTERN_MIXED_OR_UNCLEAR_FOLDERING = "mixed_or_unclear_foldering"

RULE_LOCK_ANCHOR_CANDIDATE = "lock_anchor_candidate"
RULE_IGNORE_TERM_CANDIDATE = "ignore_term_candidate"
RULE_ALIAS_CANDIDATE = "alias_candidate"
RULE_PREFERRED_GRANULARITY_CANDIDATE = "preferred_granularity_candidate"

PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"
PRIORITY_NONE = "none"

ROLE_FOLDER_NAMES = {
    "assignments",
    "assignment",
    "drafts",
    "finals",
    "final",
    "images",
    "lectures",
    "lecture",
    "midterms",
    "pe",
    "notes",
    "recitations",
    "recitation",
    "slides",
    "tutorials",
    "tutorial",
}
FORMAT_FOLDER_EXTENSIONS = {
    "pdf": ".pdf",
    "pdfs": ".pdf",
    "slides": ".pptx",
    "documents": ".docx",
    "docs": ".docx",
    "notes": ".txt",
}
ASSIGNMENT_TOKENS = {"assignment", "assignments", "submission", "submissions", "homework", "pset"}
PROJECT_NAME_STOPWORDS = ROLE_FOLDER_NAMES | set(FORMAT_FOLDER_EXTENSIONS) | {
    "downloads",
    "documents",
    "draft",
    "drafts",
    "files",
    "image",
    "images",
    "misc",
    "other",
    "resources",
    "renamed",
}
COURSE_PATTERN = re.compile(r"^[A-Za-z]{2,4}\d{4}[A-Za-z]?$")
NOISY_ANCHOR_TOKENS = {
    "builtins",
    "combined",
    "copy",
    "fixed",
    "general",
    "google",
    "headerstate",
    "java",
    "ledger",
    "mandatory",
    "modular",
    "object",
    "oriented",
    "pacing",
    "part",
    "patched",
    "pm",
    "problem",
    "programming",
    "qol",
    "roi",
    "solution",
    "solutions",
    "tracing",
}


@dataclass(frozen=True)
class OrganizationPattern:
    pattern_type: str
    confidence: int
    reason: str
    examples: tuple[str, ...]
    affected_anchors: tuple[str, ...] = ()
    supported_anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class InferredRuleCandidate:
    rule_type: str
    value: str
    confidence: int
    reason: str
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True)
class PatternInferenceResult:
    patterns: list[OrganizationPattern]
    rule_candidates: list[InferredRuleCandidate]
    anchor_evidence: dict[str, dict[str, str]]


def infer_organization_patterns(
    files: list[FileMetadata],
    anchor_decisions: list[AnchorDecision],
    min_folder_files: int = 2,
) -> PatternInferenceResult:
    eligible_files = _eligible_files(files)
    folders = _files_by_parent(eligible_files)
    needs_decision_anchors = {
        normalize_token(decision.anchor): decision.anchor
        for decision in anchor_decisions
        if decision.decision == ANCHOR_DECISION_NEEDS_DECISION
    }

    patterns: list[OrganizationPattern] = []
    rule_candidates: list[InferredRuleCandidate] = []

    course_pattern = _course_code_foldering_pattern(
        folders,
        needs_decision_anchors,
        min_folder_files,
    )
    if course_pattern is not None:
        patterns.append(course_pattern)
        rule_candidates.append(
            InferredRuleCandidate(
                rule_type=RULE_PREFERRED_GRANULARITY_CANDIDATE,
                value="course_code",
                confidence=course_pattern.confidence,
                reason="Course-code folders are already used in this root.",
                evidence_paths=_folder_evidence_paths(course_pattern.examples),
            )
        )
        rule_candidates.extend(
            _lock_anchor_candidates(
                course_pattern.supported_anchors,
                course_pattern.pattern_type,
                course_pattern.confidence,
            )
        )

    project_pattern = _project_foldering_pattern(
        folders,
        needs_decision_anchors,
        min_folder_files,
    )
    if project_pattern is not None:
        patterns.append(project_pattern)
        rule_candidates.append(
            InferredRuleCandidate(
                rule_type=RULE_PREFERRED_GRANULARITY_CANDIDATE,
                value="project",
                confidence=project_pattern.confidence,
                reason="Project-like folders are already used in this root.",
                evidence_paths=_folder_evidence_paths(project_pattern.examples),
            )
        )
        rule_candidates.extend(
            _lock_anchor_candidates(
                project_pattern.supported_anchors,
                project_pattern.pattern_type,
                project_pattern.confidence,
            )
        )

    person_pattern = _person_or_student_foldering_pattern(
        folders,
        needs_decision_anchors,
        min_folder_files,
    )
    if person_pattern is not None:
        patterns.append(person_pattern)
        rule_candidates.append(
            InferredRuleCandidate(
                rule_type=RULE_PREFERRED_GRANULARITY_CANDIDATE,
                value="person_or_student",
                confidence=person_pattern.confidence,
                reason="Sibling folders suggest person or student names may be an organization axis.",
                evidence_paths=_folder_evidence_paths(person_pattern.examples),
            )
        )
        rule_candidates.extend(
            _lock_anchor_candidates(
                person_pattern.supported_anchors,
                person_pattern.pattern_type,
                person_pattern.confidence,
            )
        )

    role_pattern = _role_foldering_pattern(
        folders,
        needs_decision_anchors,
        min_folder_files,
    )
    if role_pattern is not None:
        patterns.append(role_pattern)
        rule_candidates.append(
            InferredRuleCandidate(
                rule_type=RULE_PREFERRED_GRANULARITY_CANDIDATE,
                value="document_role",
                confidence=role_pattern.confidence,
                reason="Role folders are already used in this root.",
                evidence_paths=_folder_evidence_paths(role_pattern.examples),
            )
        )

    year_pattern = _year_foldering_pattern(folders, min_folder_files)
    if year_pattern is not None:
        patterns.append(year_pattern)
        rule_candidates.append(
            InferredRuleCandidate(
                rule_type=RULE_PREFERRED_GRANULARITY_CANDIDATE,
                value="year",
                confidence=year_pattern.confidence,
                reason="Year folders are present, but this is weak preference evidence.",
                evidence_paths=_folder_evidence_paths(year_pattern.examples),
            )
        )

    format_pattern = _format_foldering_pattern(folders, min_folder_files)
    if format_pattern is not None:
        patterns.append(format_pattern)
        rule_candidates.append(
            InferredRuleCandidate(
                rule_type=RULE_PREFERRED_GRANULARITY_CANDIDATE,
                value="file_format",
                confidence=format_pattern.confidence,
                reason="Format folders are present, but this is report-only evidence.",
                evidence_paths=_folder_evidence_paths(format_pattern.examples),
            )
        )

    patterns = sorted(
        _dedupe_patterns(patterns),
        key=lambda pattern: (-pattern.confidence, pattern.pattern_type),
    )
    rule_candidates = sorted(
        _dedupe_rule_candidates(rule_candidates),
        key=lambda candidate: (-candidate.confidence, candidate.rule_type, candidate.value),
    )
    return PatternInferenceResult(
        patterns=patterns,
        rule_candidates=rule_candidates,
        anchor_evidence=_anchor_evidence(patterns),
    )


def pattern_priority_for_anchor(
    anchor: str,
    inference: PatternInferenceResult,
) -> str:
    evidence = inference.anchor_evidence.get(normalize_token(anchor))
    if evidence is None:
        return PRIORITY_NONE
    priority = evidence.get("priority", PRIORITY_NONE)
    if priority in {PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW}:
        return priority
    return PRIORITY_NONE


def pattern_evidence_for_anchor(
    anchor: str,
    inference: PatternInferenceResult,
) -> dict[str, object] | None:
    evidence = inference.anchor_evidence.get(normalize_token(anchor))
    if evidence is None:
        return None
    return {
        "priority": evidence["priority"],
        "matched_patterns": evidence["matched_patterns"].split(","),
        "reason": evidence["reason"],
    }


def _eligible_files(files: list[FileMetadata]) -> list[FileMetadata]:
    return sorted(
        [
            metadata
            for metadata in files
            if (
                not metadata.is_dir
                and metadata.path.is_file()
                and not metadata.path.is_symlink()
                and is_allowed_organization_file(metadata, files)
                and is_actionable_source_path(metadata.relative_path, files)
            )
        ],
        key=lambda metadata: metadata.relative_path.as_posix(),
    )


def _files_by_parent(files: list[FileMetadata]) -> dict[Path, list[FileMetadata]]:
    folders: dict[Path, list[FileMetadata]] = {}
    for metadata in files:
        if metadata.relative_path.parent == Path("."):
            continue
        folders.setdefault(metadata.relative_path.parent, []).append(metadata)
    return folders


def _course_code_foldering_pattern(
    folders: dict[Path, list[FileMetadata]],
    needs_decision_anchors: dict[str, str],
    min_folder_files: int,
) -> OrganizationPattern | None:
    examples: list[str] = []
    folder_codes: dict[str, str] = {}
    for folder, folder_files in folders.items():
        code = _folder_course_code(folder.name)
        if code is None:
            continue
        if len(folder_files) < min_folder_files:
            continue
        matching_files = [
            metadata
            for metadata in folder_files
            if extract_course_code(metadata) in {code, None}
        ]
        if len(matching_files) < min_folder_files:
            continue
        folder_codes[normalize_token(code)] = code
        examples.extend(_example_paths(matching_files))

    affected = _affected_course_anchors(needs_decision_anchors, folder_codes)
    if not examples:
        return None
    return OrganizationPattern(
        pattern_type=PATTERN_COURSE_CODE_FOLDERING,
        confidence=82 if affected else 76,
        reason="Existing folders contain files whose names match their course-code folder names.",
        examples=tuple(sorted(examples)[:5]),
        affected_anchors=tuple(sorted(affected)),
        supported_anchors=tuple(sorted(folder_codes.values())),
    )


def _project_foldering_pattern(
    folders: dict[Path, list[FileMetadata]],
    needs_decision_anchors: dict[str, str],
    min_folder_files: int,
) -> OrganizationPattern | None:
    examples: list[str] = []
    folder_anchors: dict[str, str] = {}
    for folder, folder_files in folders.items():
        folder_anchor_candidates = _folder_project_anchors(
            folder.name,
            folder_files,
            needs_decision_anchors,
        )
        if not folder_anchor_candidates:
            continue
        if len(folder_files) < min_folder_files:
            continue
        for folder_anchor in folder_anchor_candidates:
            if _anchor_explains_folder_name(folder_anchor, folder.name, needs_decision_anchors):
                matching_files = folder_files
            else:
                matching_files = [
                    metadata
                    for metadata in folder_files
                    if folder_anchor in _anchor_tokens(metadata.relative_path.stem)
                ]
            if len(matching_files) < min_folder_files:
                continue
            folder_anchors[normalize_token(folder_anchor)] = _display_folder_anchor(
                folder_anchor,
                needs_decision_anchors,
            )
            examples.extend(_example_paths(matching_files))

    affected = _project_style_anchors(needs_decision_anchors, folder_anchors)
    if not examples:
        return None
    return OrganizationPattern(
        pattern_type=PATTERN_PROJECT_FOLDERING,
        confidence=76 if affected else 70,
        reason="Existing folders contain multiple files whose names match the folder's project-like anchor.",
        examples=tuple(sorted(examples)[:5]),
        affected_anchors=tuple(sorted(affected)),
        supported_anchors=tuple(sorted(folder_anchors.values())),
    )


def _person_or_student_foldering_pattern(
    folders: dict[Path, list[FileMetadata]],
    needs_decision_anchors: dict[str, str],
    min_folder_files: int,
) -> OrganizationPattern | None:
    siblings_by_parent: dict[Path, list[tuple[Path, list[FileMetadata]]]] = {}
    for folder, folder_files in folders.items():
        if len(folder_files) < min_folder_files:
            continue
        if not _looks_person_or_student_folder(folder.name, folder_files):
            continue
        siblings_by_parent.setdefault(folder.parent, []).append((folder, folder_files))

    examples: list[str] = []
    folder_names: dict[str, str] = {}
    for sibling_folders in siblings_by_parent.values():
        if len(sibling_folders) < 2:
            continue
        for folder, folder_files in sibling_folders:
            normalized = normalize_token(folder.name)
            folder_names[normalized] = needs_decision_anchors.get(normalized, folder.name)
            examples.extend(_example_paths(folder_files))

    affected = sorted(folder_names.values())
    if not examples:
        return None
    return OrganizationPattern(
        pattern_type=PATTERN_PERSON_OR_STUDENT_FOLDERING,
        confidence=72 if affected else 66,
        reason="Sibling folders look like person or student names and contain multiple document-like files.",
        examples=tuple(sorted(examples)[:5]),
        affected_anchors=tuple(sorted(affected)),
        supported_anchors=tuple(sorted(folder_names.values())),
    )


def _role_foldering_pattern(
    folders: dict[Path, list[FileMetadata]],
    needs_decision_anchors: dict[str, str],
    min_folder_files: int,
) -> OrganizationPattern | None:
    examples: list[str] = []
    role_names: dict[str, str] = {}
    for folder, folder_files in folders.items():
        role = _role_folder_name(folder.name)
        if role is None or len(folder_files) < min_folder_files:
            continue
        role_names[role] = needs_decision_anchors.get(role, _role_display(role))
        examples.extend(_example_paths(folder_files))

    affected = _anchors_with_role_files(needs_decision_anchors, role_names)
    if not examples:
        return None
    return OrganizationPattern(
        pattern_type=PATTERN_ROLE_FOLDERING,
        confidence=70 if affected else 64,
        reason="Existing role folders contain files with matching document-role names.",
        examples=tuple(sorted(examples)[:5]),
        affected_anchors=tuple(sorted(affected)),
        supported_anchors=tuple(sorted(role_names.values())),
    )


def _year_foldering_pattern(
    folders: dict[Path, list[FileMetadata]],
    min_folder_files: int,
) -> OrganizationPattern | None:
    examples: list[str] = []
    for folder, folder_files in folders.items():
        if len(folder_files) < min_folder_files:
            continue
        if re.fullmatch(r"(19|20)\d{2}", folder.name) is None:
            continue
        matching_files = [
            metadata
            for metadata in folder_files
            if folder.name in metadata.relative_path.stem
        ]
        if len(matching_files) >= min_folder_files:
            examples.extend(_example_paths(matching_files))
    if len(_folder_evidence_paths(tuple(examples))) < 2:
        return None
    return OrganizationPattern(
        pattern_type=PATTERN_YEAR_FOLDERING,
        confidence=54,
        reason="Several year folders contain files that also reference the folder year.",
        examples=tuple(sorted(examples)[:5]),
    )


def _format_foldering_pattern(
    folders: dict[Path, list[FileMetadata]],
    min_folder_files: int,
) -> OrganizationPattern | None:
    examples: list[str] = []
    for folder, folder_files in folders.items():
        expected_extension = FORMAT_FOLDER_EXTENSIONS.get(normalize_token(folder.name))
        if expected_extension is None or len(folder_files) < min_folder_files:
            continue
        matching_files = [
            metadata
            for metadata in folder_files
            if metadata.extension.lower() == expected_extension
        ]
        if len(matching_files) / len(folder_files) >= 0.75:
            examples.extend(_example_paths(matching_files))
    if not examples:
        return None
    return OrganizationPattern(
        pattern_type=PATTERN_FORMAT_FOLDERING,
        confidence=58,
        reason="Existing format folders contain mostly one document format.",
        examples=tuple(sorted(examples)[:5]),
    )


def _affected_course_anchors(
    needs_decision_anchors: dict[str, str],
    folder_codes: dict[str, str],
) -> list[str]:
    if not folder_codes:
        return []
    return [
        display
        for normalized, display in needs_decision_anchors.items()
        if normalized in folder_codes
    ]


def _matching_needs_decision_anchors(
    needs_decision_anchors: dict[str, str],
    observed_anchors: dict[str, str],
) -> list[str]:
    return [
        display
        for normalized, display in needs_decision_anchors.items()
        if normalized in observed_anchors
    ]


def _project_style_anchors(
    needs_decision_anchors: dict[str, str],
    observed_anchors: dict[str, str],
) -> list[str]:
    if not observed_anchors:
        return []
    return [
        display
        for normalized, display in needs_decision_anchors.items()
        if normalized in observed_anchors
    ]


def _person_style_anchors(
    needs_decision_anchors: dict[str, str],
    observed_anchors: dict[str, str],
) -> list[str]:
    if not observed_anchors:
        return []
    return [
        display
        for normalized, display in needs_decision_anchors.items()
        if normalized in observed_anchors
    ]


def _anchors_with_role_files(
    needs_decision_anchors: dict[str, str],
    roles: dict[str, str],
) -> list[str]:
    if not roles:
        return []
    return [
        display
        for normalized, display in needs_decision_anchors.items()
        if normalized in roles
    ]


def _anchor_evidence(
    patterns: list[OrganizationPattern],
) -> dict[str, dict[str, str]]:
    evidence: dict[str, dict[str, str]] = {}
    for pattern in patterns:
        for anchor in pattern.affected_anchors:
            priority = _priority_for_pattern(pattern, anchor)
            normalized = normalize_token(anchor)
            current = evidence.get(normalized)
            if current is None:
                evidence[normalized] = {
                    "priority": priority,
                    "matched_patterns": pattern.pattern_type,
                    "reason": _pattern_anchor_reason(pattern.pattern_type),
                }
                continue
            current_priority = current["priority"]
            if _priority_rank(priority) < _priority_rank(current_priority):
                current["priority"] = priority
                current["reason"] = _pattern_anchor_reason(pattern.pattern_type)
            matched_patterns = set(current["matched_patterns"].split(","))
            matched_patterns.add(pattern.pattern_type)
            current["matched_patterns"] = ",".join(sorted(matched_patterns))
    return evidence


def _priority_for_pattern(pattern: OrganizationPattern, anchor: str) -> str:
    score = _pattern_anchor_score(pattern, anchor)
    if score >= 60:
        return PRIORITY_HIGH
    if score >= 40:
        return PRIORITY_MEDIUM
    if score >= 25:
        return PRIORITY_LOW
    return PRIORITY_NONE


def _pattern_anchor_score(pattern: OrganizationPattern, anchor: str) -> int:
    normalized_anchor = normalize_token(anchor)
    normalized_supported = {normalize_token(item) for item in pattern.supported_anchors}
    score = 0
    if normalized_anchor in normalized_supported:
        score += 40
    if pattern.pattern_type == PATTERN_PERSON_OR_STUDENT_FOLDERING:
        score += 25
    if pattern.pattern_type in {
        PATTERN_COURSE_CODE_FOLDERING,
        PATTERN_PROJECT_FOLDERING,
        PATTERN_ROLE_FOLDERING,
    }:
        score += 15
    if len(pattern.examples) >= 2:
        score += 10
    if _is_noisy_anchor(anchor):
        score -= 40
    return score


def _priority_rank(priority: str) -> int:
    return {
        PRIORITY_HIGH: 0,
        PRIORITY_MEDIUM: 1,
        PRIORITY_LOW: 2,
        PRIORITY_NONE: 3,
    }.get(priority, 99)


def _pattern_anchor_reason(pattern_type: str) -> str:
    if pattern_type == PATTERN_COURSE_CODE_FOLDERING:
        return "Existing folders suggest this root may group course materials by module code."
    if pattern_type == PATTERN_PROJECT_FOLDERING:
        return "Existing folders suggest project-name grouping may match this root."
    if pattern_type == PATTERN_PERSON_OR_STUDENT_FOLDERING:
        return "Existing sibling folders suggest person or student names may be an organization axis."
    if pattern_type == PATTERN_ROLE_FOLDERING:
        return "Existing folders suggest document role may be an organization axis."
    return "Existing folders provide weak local preference evidence for this anchor."


def _role_display(role: str) -> str:
    return {
        "assignment": "Assignments",
        "draft": "Drafts",
        "final": "Finals",
        "image": "Images",
        "lecture": "Lectures",
        "midterm": "Midterms",
        "notes": "Notes",
        "pe": "PE",
        "recitation": "Recitations",
        "slides": "Slides",
        "tutorial": "Tutorials",
    }.get(role, role.capitalize())


def _is_noisy_anchor(anchor: str) -> bool:
    normalized = normalize_token(anchor)
    compact = normalized.replace("_", "")
    if normalized in NOISY_ANCHOR_TOKENS or compact in NOISY_ANCHOR_TOKENS:
        return True
    if re.fullmatch(r"v\d+", normalized):
        return True
    if re.fullmatch(r"\d{1,2}_[a-z0-9_]+", normalized):
        return True
    if re.fullmatch(r"[a-z]\d{12,}", normalized):
        return True
    if re.fullmatch(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\d{2,4}", normalized):
        return True
    return False


def _lock_anchor_candidates(
    anchors: tuple[str, ...],
    pattern_type: str,
    confidence: int,
) -> list[InferredRuleCandidate]:
    return [
        InferredRuleCandidate(
            rule_type=RULE_LOCK_ANCHOR_CANDIDATE,
            value=anchor,
            confidence=max(50, confidence - 5),
            reason=f"{anchor} matches existing {pattern_type} evidence, but locking it is a manual rule decision.",
            evidence_paths=(),
        )
        for anchor in anchors
    ]


def _dedupe_patterns(patterns: list[OrganizationPattern]) -> list[OrganizationPattern]:
    by_type: dict[str, OrganizationPattern] = {}
    for pattern in patterns:
        current = by_type.get(pattern.pattern_type)
        if current is None or pattern.confidence > current.confidence:
            by_type[pattern.pattern_type] = pattern
    return list(by_type.values())


def _dedupe_rule_candidates(
    candidates: list[InferredRuleCandidate],
) -> list[InferredRuleCandidate]:
    by_key: dict[tuple[str, str], InferredRuleCandidate] = {}
    for candidate in candidates:
        key = (candidate.rule_type, candidate.value)
        current = by_key.get(key)
        if current is None or candidate.confidence > current.confidence:
            by_key[key] = candidate
    return list(by_key.values())


def _folder_evidence_paths(examples: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    folders = {
        Path(example).parent.as_posix()
        for example in examples
        if Path(example).parent.as_posix() not in {"", "."}
    }
    return tuple(sorted(folders))


def _display_folder_anchor(
    anchor: str,
    needs_decision_anchors: dict[str, str],
) -> str:
    normalized = normalize_token(anchor)
    if normalized in needs_decision_anchors:
        return needs_decision_anchors[normalized]
    if "_" in anchor:
        return "_".join(part.capitalize() for part in anchor.split("_"))
    if anchor.isupper():
        return anchor
    return anchor.capitalize()


def _example_paths(files: list[FileMetadata]) -> list[str]:
    return [metadata.relative_path.as_posix() for metadata in files[:3]]


def _folder_course_code(folder_name: str) -> str | None:
    for token in _folder_tokens(folder_name):
        if COURSE_PATTERN.fullmatch(token) is not None:
            return token.upper()
    return None


def _folder_project_anchors(
    folder_name: str,
    folder_files: list[FileMetadata],
    needs_decision_anchors: dict[str, str],
) -> list[str]:
    raw_tokens = _folder_tokens(folder_name)
    normalized_tokens = [normalize_token(token) for token in raw_tokens]
    file_anchor_tokens = {
        token
        for metadata in folder_files
        for token in _anchor_tokens(metadata.relative_path.stem)
    }
    candidates: list[str] = []

    if len(normalized_tokens) >= 2 and ("_" in folder_name or "-" in folder_name):
        first_two = normalized_tokens[:2]
        if all(_is_project_anchor_token(token) for token in first_two):
            candidates.append("_".join(first_two))

    for raw_token, normalized in zip(raw_tokens, normalized_tokens):
        if not _is_project_anchor_token(normalized):
            continue
        if COURSE_PATTERN.fullmatch(raw_token) is not None:
            continue
        if _looks_name_like(raw_token):
            continue
        if normalized in needs_decision_anchors:
            candidates.append(normalized)
            continue
        if (
            any(character.isupper() for character in raw_token[1:])
            or "_" in folder_name
            or "-" in folder_name
            or normalized in file_anchor_tokens
        ):
            candidates.append(normalized)

    return sorted(set(candidates))


def _anchor_explains_folder_name(
    anchor: str,
    folder_name: str,
    needs_decision_anchors: dict[str, str],
) -> bool:
    normalized_anchor = normalize_token(anchor)
    folder_tokens = [normalize_token(token) for token in _folder_tokens(folder_name)]
    if normalized_anchor in folder_tokens and normalized_anchor in needs_decision_anchors:
        return True
    if "_" in normalized_anchor:
        joined = "_".join(folder_tokens[: len(normalized_anchor.split("_"))])
        return joined == normalized_anchor and normalized_anchor in needs_decision_anchors
    return False


def _is_project_anchor_token(token: str) -> bool:
    return len(token) > 1 and token not in PROJECT_NAME_STOPWORDS and not token.isdigit()


def _looks_person_or_student_folder(folder_name: str, folder_files: list[FileMetadata]) -> bool:
    if not _looks_name_like(folder_name):
        return False
    token_sets = [_path_tokens(metadata.relative_path.stem) for metadata in folder_files]
    return any(tokens & ASSIGNMENT_TOKENS for tokens in token_sets) or len(folder_files) >= 2


def _looks_name_like(value: str) -> bool:
    parts = value.replace("_", " ").replace("-", " ").split()
    return 1 <= len(parts) <= 2 and all(
        len(part) >= 2 and part[0].isupper() and part[1:].islower()
        for part in parts
    )


def _role_folder_name(folder_name: str) -> str | None:
    for normalized in [normalize_token(token) for token in _folder_tokens(folder_name)]:
        if normalized not in ROLE_FOLDER_NAMES:
            continue
        return {
            "assignment": "assignment",
            "assignments": "assignment",
            "drafts": "draft",
            "finals": "final",
            "final": "final",
            "images": "image",
            "lecture": "lecture",
            "lectures": "lecture",
            "midterms": "midterm",
            "pe": "pe",
            "recitation": "recitation",
            "recitations": "recitation",
            "slides": "slides",
            "tutorial": "tutorial",
            "tutorials": "tutorial",
        }.get(normalized, normalized)
    return None


def _folder_tokens(folder_name: str) -> list[str]:
    return [
        token
        for token in re.split(r"[^A-Za-z0-9]+", folder_name)
        if token
    ]


def _path_tokens(value: str) -> set[str]:
    return {
        normalize_token(token)
        for token in re.split(r"[^A-Za-z0-9]+", value)
        if token
    }


def _anchor_tokens(value: str) -> set[str]:
    tokens = _path_tokens(value)
    raw_tokens = [
        token
        for token in re.split(r"[^A-Za-z0-9]+", value)
        if token
    ]
    if len(raw_tokens) >= 2:
        tokens.add("_".join(normalize_token(token) for token in raw_tokens[:2]))
    return tokens
