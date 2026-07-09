import re
from dataclasses import dataclass
from pathlib import Path

from organizer.models import (
    FileMetadata,
    MovePlanItem,
    OrganizationSuggestion,
    ProjectGroup,
)
from organizer.organization_rules import (
    OrganizationRules,
    canonical_anchor,
    default_organization_rules,
    display_anchor,
)
from organizer.review import detect_review_candidates
from organizer.scope import is_allowed_organization_file

WEAK_TOKENS = {
    "final",
    "draft",
    "copy",
    "backup",
    "old",
    "new",
    "version",
    "v",
    "the",
    "and",
    "file",
    "document",
    "screenshot",
}
WEAK_GROUP_TOKENS = WEAK_TOKENS | {
    "balanced",
    "data",
    "debug",
    "field",
    "full",
    "image",
    "index",
    "other",
    "output",
    "report",
    "resource",
    "results",
    "run",
    "summary",
    "updated",
    "v1",
    "v2",
    "v3",
}
GROUP_EVIDENCE_COURSE_CODE = "course_code"
GROUP_EVIDENCE_NAMED_PROJECT = "named_project"
GROUP_EVIDENCE_STRUCTURED_SERIES = "structured_series"
GROUP_EVIDENCE_LOCKED_ANCHOR = "locked_anchor"
GROUP_EVIDENCE_NEEDS_DECISION = "needs_decision"
GROUP_EVIDENCE_BROAD_ANCHOR = "broad_anchor"
GROUP_EVIDENCE_YEAR_VARIANT_SET = "year_variant_set"
GROUP_EVIDENCE_NUMBERED_SERIES = "numbered_series"
GROUP_EVIDENCE_QUESTION_SOLUTION_SET = "question_solution_set"
GROUP_EVIDENCE_TITLE_VARIANT_SET = "title_variant_set"
ALLOWED_ORGANIZATION_EVIDENCE = {
    GROUP_EVIDENCE_LOCKED_ANCHOR,
    GROUP_EVIDENCE_YEAR_VARIANT_SET,
    GROUP_EVIDENCE_NUMBERED_SERIES,
    GROUP_EVIDENCE_QUESTION_SOLUTION_SET,
    GROUP_EVIDENCE_TITLE_VARIANT_SET,
}
COURSE_CODE_PATTERN = re.compile(r"[A-Za-z]{2,4}\d{4}[A-Za-z]?")
PAPER_TOKENS = {"paper", "article", "journal", "reading", "reference"}
RESULT_TOKENS = {"result", "results", "output", "experiment", "eval", "evaluation"}
CODE_EXTENSIONS = {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".html", ".css", ".ipynb"}
DATASET_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".json", ".parquet"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".rar", ".7z"}
DOCUMENT_EXTENSIONS = {".doc", ".docx", ".odt", ".pages"}
EXAM_TOKENS = {"exam", "final", "finals", "midterm", "pe", "solution", "solutions", "answer", "answers"}
RECITATION_TOKENS = {"recitation", "rec"}
TUTORIAL_TOKENS = {"tutorial", "tut"}
PRACTICAL_TOKENS = {"practical", "lab", "mission", "contest", "exercise"}
LECTURE_TOKENS = {"lecture", "lec", "lesson"}
ASSIGNMENT_TOKENS = {"assignment", "homework", "pset"}
ADMIN_TOKENS = {"syllabus", "schedule", "rubric", "briefing", "form"}
NOTE_TOKENS = {"note", "notes", "summary", "cheatsheet", "guide"}
NARROW_ROLE_TOKENS = (
    EXAM_TOKENS
    | RECITATION_TOKENS
    | TUTORIAL_TOKENS
    | PRACTICAL_TOKENS
    | LECTURE_TOKENS
    | ASSIGNMENT_TOKENS
    | {"slide", "slides", "project"}
)
QUESTION_SOLUTION_TOKENS = {"solution", "solutions", "answer", "answers", "key"}
TITLE_VARIANT_TOKENS = {
    "copy",
    "duplicate",
    "duplicated",
    "draft",
    "final",
    "finalfinal",
    "new",
    "old",
    "previous",
    "prev",
    "version",
    "v1",
    "v2",
    "v3",
}
ANCHOR_DECISION_SUGGESTED = "suggested"
ANCHOR_DECISION_NEEDS_DECISION = "needs_decision"
ANCHOR_DECISION_IGNORED = "ignored"
GENERIC_ANCHOR_TERMS = WEAK_GROUP_TOKENS | {
    "chat",
    "export",
    "exports",
    "file",
    "files",
    "img",
    "instructions",
    "module",
    "modules",
    "note",
    "notes",
    "page",
    "pasted",
    "resources",
    "untitled",
}


@dataclass(frozen=True)
class AnchorDecision:
    anchor: str
    decision: str
    reason: str
    evidence: str
    file_count: int
    files: list[FileMetadata]
    examples: list[str]


@dataclass(frozen=True)
class _AnchorCandidate:
    key: str
    display_name: str
    evidence: str


def normalize_token(text: str) -> str:
    return text.lower().strip()


def extract_filename_tokens(file: FileMetadata) -> set[str]:
    tokens = set()
    for token in re.split(r"[^a-z0-9]+", file.relative_path.stem.lower()):
        normalized = normalize_token(token)
        if len(normalized) <= 1 or normalized in WEAK_TOKENS:
            continue
        tokens.add(normalized)
    return tokens


def extract_course_code(file: FileMetadata) -> str | None:
    match = COURSE_CODE_PATTERN.search(file.relative_path.as_posix())
    if match is None:
        return None
    return match.group(0).upper()


def infer_subfolder(file: FileMetadata) -> str:
    extension = file.extension.lower()
    tokens = extract_filename_tokens(file)

    if extension == ".pdf" and tokens & PAPER_TOKENS:
        return "papers"
    if extension in {".md", ".txt", ".rtf"}:
        return "notes"
    if extension in CODE_EXTENSIONS:
        return "code"
    if extension in DATASET_EXTENSIONS:
        return "datasets"
    if tokens & RESULT_TOKENS:
        return "results"
    if extension in {".ppt", ".pptx", ".key"}:
        return "slides"
    if extension in IMAGE_EXTENSIONS:
        return "images"
    if extension in ARCHIVE_EXTENSIONS:
        return "archives"
    if extension in DOCUMENT_EXTENSIONS:
        return "documents"
    return "other"


def infer_role_subfolder(file: FileMetadata) -> str:
    extension = file.extension.lower()
    stem = file.relative_path.stem.lower()
    tokens = _all_filename_tokens(file)

    if extension in {".ppt", ".pptx", ".key"}:
        return "slides"
    if "practical exam" in stem:
        return "exams"
    if tokens & EXAM_TOKENS or "answer key" in stem or "past year" in stem:
        return "exams"
    if tokens & RECITATION_TOKENS:
        return "recitations"
    if tokens & TUTORIAL_TOKENS:
        return "tutorials"
    if tokens & PRACTICAL_TOKENS:
        return "practicals"
    if tokens & LECTURE_TOKENS:
        return "lectures"
    if tokens & ASSIGNMENT_TOKENS or "problem set" in stem:
        return "assignments"
    if tokens & ADMIN_TOKENS:
        return "admin"
    if tokens & PAPER_TOKENS or "doi" in tokens or "research" in tokens:
        return "papers"
    if extension in {".md", ".txt", ".rtf"} or tokens & NOTE_TOKENS:
        return "notes"
    return "other"


def find_project_groups(
    files: list[FileMetadata],
    review_folder_name: str = "AI_Review",
    min_group_size: int = 2,
    rules: OrganizationRules | None = None,
) -> list[ProjectGroup]:
    anchor_decisions = analyze_anchor_decisions(
        files,
        review_folder_name=review_folder_name,
        min_group_size=min_group_size,
        rules=rules,
    )
    assigned_paths: set[Path] = set()
    groups: list[ProjectGroup] = []

    for decision in anchor_decisions:
        if decision.decision != ANCHOR_DECISION_SUGGESTED:
            continue
        available_files = [
            file
            for file in decision.files
            if file.relative_path not in assigned_paths
        ]
        if len(available_files) < min_group_size:
            continue
        sorted_files = _sort_files(available_files)
        confidence = 90 if decision.evidence == GROUP_EVIDENCE_COURSE_CODE else 80
        groups.append(
            ProjectGroup(
                group_name=decision.anchor,
                files=sorted_files,
                reason=decision.reason,
                confidence=confidence,
            )
        )
        assigned_paths.update(file.relative_path for file in sorted_files)

    return sorted(groups, key=lambda group: (-group.confidence, group.group_name))


def analyze_anchor_decisions(
    files: list[FileMetadata],
    review_folder_name: str = "AI_Review",
    min_group_size: int = 2,
    rules: OrganizationRules | None = None,
) -> list[AnchorDecision]:
    active_rules = rules or default_organization_rules()
    eligible_files = _eligible_files(files, review_folder_name)
    buckets: dict[str, dict[str, object]] = {}

    for file in eligible_files:
        for candidate in _anchor_candidates_for_file(file, active_rules):
            _add_anchor_candidate(buckets, candidate, file)

    decisions: list[AnchorDecision] = []
    for canonical, bucket in buckets.items():
        bucket_files = bucket["files"]
        bucket_evidence = bucket["evidence"]
        if not isinstance(bucket_files, list) or not isinstance(bucket_evidence, set):
            continue
        unique_files = _unique_sorted_files(bucket_files)
        if len(unique_files) < min_group_size:
            continue
        evidence = _best_evidence(bucket_evidence)
        if evidence in ALLOWED_ORGANIZATION_EVIDENCE and not _valid_narrow_or_locked_group(
            canonical,
            evidence,
            unique_files,
        ):
            continue
        display_name = str(bucket["display"])
        decision, reason, final_evidence = _anchor_decision(
            canonical,
            display_name,
            evidence,
            len(unique_files),
            active_rules,
        )
        decisions.append(
            AnchorDecision(
                anchor=display_name,
                decision=decision,
                reason=reason,
                evidence=final_evidence,
                file_count=len(unique_files),
                files=unique_files,
                examples=[
                    file.relative_path.as_posix()
                    for file in unique_files[:3]
                ],
            )
        )

    return sorted(
        decisions,
        key=lambda item: (
            _anchor_decision_sort_rank(item.decision),
            _evidence_rank(item.evidence),
            -item.file_count,
            item.anchor,
        ),
    )


def build_organization_suggestions(
    groups: list[ProjectGroup],
    root: Path,
    organized_folder_name: str = "Organized",
) -> list[OrganizationSuggestion]:
    suggestions: list[OrganizationSuggestion] = []

    for group in sorted(groups, key=lambda item: item.group_name):
        safe_group_name = _safe_group_name(group.group_name)
        suggested_root = root / organized_folder_name / safe_group_name
        plan_items: list[MovePlanItem] = []
        used_destinations: set[Path] = set()

        for file in _sort_files(group.files):
            if not is_allowed_organization_file(file, group.files):
                continue
            subfolder = infer_role_subfolder(file)
            destination = suggested_root / subfolder / file.name
            destination = _avoid_destination_collision(
                destination,
                file,
                used_destinations,
            )
            used_destinations.add(destination)
            plan_items.append(
                MovePlanItem(
                    source=file.path,
                    destination=destination,
                    reason=f"{group.reason}; suggested subfolder {subfolder}",
                    confidence=group.confidence,
                    operation="dry-run move",
                    overwrite_risk=destination.exists(),
                )
            )

        if plan_items:
            suggestions.append(
                OrganizationSuggestion(
                    group=group,
                    suggested_root=suggested_root,
                    plan_items=plan_items,
                )
            )

    return suggestions


def _eligible_files(
    files: list[FileMetadata],
    review_folder_name: str,
) -> list[FileMetadata]:
    review_candidate_paths = {
        candidate.file.relative_path
        for candidate in detect_review_candidates(files, review_folder_name)
    }
    eligible = []
    for file in files:
        if file.is_dir or file.path.is_symlink() or not file.path.is_file():
            continue
        if _is_under_folder(file.relative_path, review_folder_name):
            continue
        if file.relative_path in review_candidate_paths:
            continue
        if not is_allowed_organization_file(file, files):
            continue
        eligible.append(file)
    return _sort_files(eligible)


def _anchor_candidates_for_file(
    file: FileMetadata,
    rules: OrganizationRules,
) -> list[_AnchorCandidate]:
    candidates: list[_AnchorCandidate] = []
    course_code = extract_course_code(file)
    if course_code is not None:
        canonical = canonical_anchor(course_code, rules)
        candidates.append(
            _AnchorCandidate(
                key=canonical,
                display_name=display_anchor(course_code, rules, course_code),
                evidence=GROUP_EVIDENCE_COURSE_CODE,
            )
        )

    for anchor, display_name in _named_anchor_candidates(file):
        canonical = canonical_anchor(anchor, rules)
        candidates.append(
            _AnchorCandidate(
                key=canonical,
                display_name=display_anchor(anchor, rules, display_name),
                evidence=GROUP_EVIDENCE_NAMED_PROJECT,
            )
        )

    for token, display_name in _all_anchor_tokens(file):
        canonical = canonical_anchor(token, rules)
        candidates.append(
            _AnchorCandidate(
                key=canonical,
                display_name=display_anchor(token, rules, display_name),
                evidence=GROUP_EVIDENCE_NEEDS_DECISION,
            )
        )

    candidates.extend(_narrow_anchor_candidates(file, rules))

    return _dedupe_anchor_candidates(candidates)


def _add_anchor_candidate(
    buckets: dict[str, dict[str, object]],
    candidate: _AnchorCandidate,
    file: FileMetadata,
) -> None:
    bucket = buckets.setdefault(
        candidate.key,
        {
            "display": candidate.display_name,
            "files": [],
            "evidence": set(),
        },
    )
    bucket_files = bucket["files"]
    if isinstance(bucket_files, list):
        bucket_files.append(file)
    bucket_evidence = bucket["evidence"]
    if isinstance(bucket_evidence, set):
        bucket_evidence.add(candidate.evidence)


def _narrow_anchor_candidates(
    file: FileMetadata,
    rules: OrganizationRules,
) -> list[_AnchorCandidate]:
    base = _primary_anchor(file, rules)
    if base is None:
        return []
    base_key, base_display = base
    if base_key in rules.ignored_terms or _is_default_ignored_anchor(base_key):
        return []
    if _looks_personal_name_anchor(base_display) and base_key not in rules.locked_anchors:
        return []

    tokens = _token_sequence(file)
    candidates: list[_AnchorCandidate] = []
    role = _primary_role_token(tokens)
    if role is not None:
        role_display = _role_display(role)
        key = f"{base_key} {role}"
        display = f"{base_display} {role_display}"
        if _year_or_term_tokens(tokens):
            candidates.append(
                _AnchorCandidate(key, display, GROUP_EVIDENCE_YEAR_VARIANT_SET)
            )
        if _number_tokens(tokens):
            candidates.append(
                _AnchorCandidate(key, display, GROUP_EVIDENCE_NUMBERED_SERIES)
            )

    solution_base = _solution_pair_base(tokens, base_key, base_display)
    if solution_base is not None:
        candidates.append(solution_base)

    title_variant = _title_variant_candidate(tokens, base_key, base_display, file)
    if title_variant is not None:
        candidates.append(title_variant)

    return candidates


def _primary_anchor(
    file: FileMetadata,
    rules: OrganizationRules,
) -> tuple[str, str] | None:
    course_code = extract_course_code(file)
    if course_code is not None:
        canonical = canonical_anchor(course_code, rules)
        return canonical, display_anchor(course_code, rules, course_code)
    named = _named_anchor_candidates(file)
    if named:
        anchor, display_name = named[0]
        canonical = canonical_anchor(anchor, rules)
        return canonical, display_anchor(anchor, rules, display_name)
    return None


def _all_anchor_tokens(file: FileMetadata) -> list[tuple[str, str]]:
    stem = file.relative_path.stem
    raw_tokens = [token for token in re.split(r"[^A-Za-z0-9]+", stem) if token]
    candidates: list[tuple[str, str]] = []
    for raw_token in raw_tokens:
        normalized = normalize_token(raw_token)
        if len(normalized) <= 1:
            continue
        candidates.append((normalized, _display_anchor(raw_token)))
    return candidates


def _dedupe_anchor_candidates(
    candidates: list[_AnchorCandidate],
) -> list[_AnchorCandidate]:
    best_by_anchor: dict[str, _AnchorCandidate] = {}
    for candidate in candidates:
        normalized = normalize_token(candidate.key)
        current = best_by_anchor.get(normalized)
        if current is None or _evidence_rank(candidate.evidence) < _evidence_rank(current.evidence):
            best_by_anchor[normalized] = _AnchorCandidate(
                key=normalized,
                display_name=candidate.display_name,
                evidence=candidate.evidence,
            )
    return list(best_by_anchor.values())


def _anchor_decision(
    canonical: str,
    display_name: str,
    evidence: str,
    file_count: int,
    rules: OrganizationRules,
) -> tuple[str, str, str]:
    if canonical in rules.ignored_terms or _is_default_ignored_anchor(canonical):
        return (
            ANCHOR_DECISION_IGNORED,
            f"anchor {display_name} is ignored by organization rules or conservative defaults",
            evidence,
        )
    if canonical in rules.locked_anchors:
        return (
            ANCHOR_DECISION_SUGGESTED,
            f"files share locked anchor {display_name}; evidence {GROUP_EVIDENCE_LOCKED_ANCHOR}",
            GROUP_EVIDENCE_LOCKED_ANCHOR,
        )
    if evidence in {
        GROUP_EVIDENCE_YEAR_VARIANT_SET,
        GROUP_EVIDENCE_NUMBERED_SERIES,
        GROUP_EVIDENCE_QUESTION_SOLUTION_SET,
        GROUP_EVIDENCE_TITLE_VARIANT_SET,
    }:
        return (
            ANCHOR_DECISION_SUGGESTED,
            _narrow_reason(display_name, evidence),
            evidence,
        )
    if evidence == GROUP_EVIDENCE_COURSE_CODE:
        return (
            ANCHOR_DECISION_NEEDS_DECISION,
            f"Broad course/module anchor. Lock {display_name} if you want all matching files grouped together.",
            GROUP_EVIDENCE_BROAD_ANCHOR,
        )
    return (
        ANCHOR_DECISION_NEEDS_DECISION,
        f"Broad anchor {display_name} appears in {file_count} eligible files and may depend on your organization preference.",
        GROUP_EVIDENCE_BROAD_ANCHOR,
    )


def _narrow_reason(display_name: str, evidence: str) -> str:
    if evidence == GROUP_EVIDENCE_YEAR_VARIANT_SET:
        return f"Files appear to be the same document set across years or terms: {display_name}"
    if evidence == GROUP_EVIDENCE_NUMBERED_SERIES:
        return f"Files appear to be a numbered continuous document series: {display_name}"
    if evidence == GROUP_EVIDENCE_QUESTION_SOLUTION_SET:
        return f"Files appear to be a question/solution document pair: {display_name}"
    if evidence == GROUP_EVIDENCE_TITLE_VARIANT_SET:
        return f"Files appear to be variants of the same document title: {display_name}"
    return f"Files appear to be a narrow document set: {display_name}"


def _is_default_ignored_anchor(anchor: str) -> bool:
    return (
        anchor in GENERIC_ANCHOR_TERMS
        or bool(re.fullmatch(r"\d{1,4}", anchor))
        or bool(re.fullmatch(r"20\d{2}|19\d{2}", anchor))
    )


def _valid_narrow_or_locked_group(
    canonical: str,
    evidence: str,
    files: list[FileMetadata],
) -> bool:
    if evidence == GROUP_EVIDENCE_LOCKED_ANCHOR:
        return True
    if evidence == GROUP_EVIDENCE_YEAR_VARIANT_SET:
        return len(_variant_values(files, _year_or_term_tokens)) >= 2
    if evidence == GROUP_EVIDENCE_NUMBERED_SERIES:
        numbers = sorted(_variant_values(files, _number_tokens))
        if len(numbers) < 2:
            return False
        numeric_values = sorted(int(number) for number in numbers)
        return numeric_values == list(range(numeric_values[0], numeric_values[-1] + 1))
    if evidence == GROUP_EVIDENCE_QUESTION_SOLUTION_SET:
        has_solution = any(_has_solution_token(_token_sequence(file)) for file in files)
        has_question = any(not _has_solution_token(_token_sequence(file)) for file in files)
        return has_solution and has_question
    if evidence == GROUP_EVIDENCE_TITLE_VARIANT_SET:
        extensions = {file.extension.lower() for file in files}
        has_variant = any(_has_title_variant_token(_token_sequence(file)) for file in files)
        return has_variant or len(extensions) >= 2
    return False


def _variant_values(
    files: list[FileMetadata],
    extractor,
) -> set[str]:
    values: set[str] = set()
    for file in files:
        values.update(extractor(_token_sequence(file)))
    return values


def _token_sequence(file: FileMetadata) -> list[str]:
    return [
        normalize_token(token)
        for token in re.split(r"[^A-Za-z0-9]+", file.relative_path.stem)
        if token
    ]


def _primary_role_token(tokens: list[str]) -> str | None:
    normalized_roles = {
        "finals": "finals",
        "final": "finals",
        "exam": "exam",
        "exams": "exam",
        "midterm": "midterm",
        "recitation": "recitation",
        "rec": "recitation",
        "tutorial": "tutorial",
        "tut": "tutorial",
        "lecture": "lecture",
        "lec": "lecture",
        "assignment": "assignment",
        "homework": "assignment",
        "slides": "slides",
        "slide": "slides",
        "project": "project",
    }
    for token in tokens:
        if token in normalized_roles:
            return normalized_roles[token]
    return None


def _role_display(role: str) -> str:
    return role.replace("_", " ")


def _year_or_term_tokens(tokens: list[str]) -> set[str]:
    values: set[str] = set()
    month_pattern = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\d{2,4}$")
    term_pattern = re.compile(r"^(spring|summer|fall|autumn|winter)\d{2,4}$")
    for token in tokens:
        if re.fullmatch(r"(19|20)\d{2}", token):
            values.add(token)
        elif month_pattern.fullmatch(token) or term_pattern.fullmatch(token):
            values.add(token)
    return values


def _number_tokens(tokens: list[str]) -> set[str]:
    return {
        str(int(token))
        for token in tokens
        if re.fullmatch(r"\d{1,3}", token)
    }


def _solution_pair_base(
    tokens: list[str],
    base_key: str,
    base_display: str,
) -> _AnchorCandidate | None:
    role = _primary_role_token(tokens)
    if role is None:
        return None
    term_tokens = sorted(_year_or_term_tokens(tokens))
    if not term_tokens:
        return None
    term = term_tokens[0]
    display = f"{base_display} {_role_display(role)} {term}"
    return _AnchorCandidate(
        key=f"{base_key} {role} {term}",
        display_name=display,
        evidence=GROUP_EVIDENCE_QUESTION_SOLUTION_SET,
    )


def _title_variant_candidate(
    tokens: list[str],
    base_key: str,
    base_display: str,
    file: FileMetadata,
) -> _AnchorCandidate | None:
    title_tokens = _title_tokens_after_base(tokens, base_key)
    if len(title_tokens) < 2:
        return None
    stripped_tokens = [
        token
        for token in title_tokens
        if token not in TITLE_VARIANT_TOKENS and token not in _year_or_term_tokens(tokens)
    ]
    if len(stripped_tokens) < 2:
        return None
    title = " ".join(stripped_tokens)
    display = f"{base_display} {title}"
    return _AnchorCandidate(
        key=f"{base_key} {title}",
        display_name=display,
        evidence=GROUP_EVIDENCE_TITLE_VARIANT_SET,
    )


def _title_tokens_after_base(tokens: list[str], base_key: str) -> list[str]:
    base_parts = base_key.split()
    if tokens[: len(base_parts)] == base_parts:
        return tokens[len(base_parts) :]
    if tokens and tokens[0] == base_key:
        return tokens[1:]
    course_index = next(
        (
            index
            for index, token in enumerate(tokens)
            if token == base_key
        ),
        -1,
    )
    if course_index >= 0:
        return tokens[:course_index] + tokens[course_index + 1 :]
    return tokens[1:]


def _has_solution_token(tokens: list[str]) -> bool:
    return bool(set(tokens) & QUESTION_SOLUTION_TOKENS)


def _has_title_variant_token(tokens: list[str]) -> bool:
    return bool(set(tokens) & TITLE_VARIANT_TOKENS)


def _looks_personal_name_anchor(display_name: str) -> bool:
    parts = display_name.replace("_", " ").split()
    if not 1 <= len(parts) <= 2:
        return False
    return all(_is_title_case_word(part) for part in parts)


def _is_title_case_word(value: str) -> bool:
    return (
        len(value) >= 2
        and value[0].isupper()
        and value[1:].islower()
        and value.isalpha()
    )


def _best_evidence(evidence_values: set[str]) -> str:
    return sorted(evidence_values, key=_evidence_rank)[0]


def _evidence_rank(evidence: str) -> int:
    return {
        GROUP_EVIDENCE_LOCKED_ANCHOR: 0,
        GROUP_EVIDENCE_YEAR_VARIANT_SET: 1,
        GROUP_EVIDENCE_NUMBERED_SERIES: 2,
        GROUP_EVIDENCE_QUESTION_SOLUTION_SET: 3,
        GROUP_EVIDENCE_TITLE_VARIANT_SET: 4,
        GROUP_EVIDENCE_COURSE_CODE: 5,
        GROUP_EVIDENCE_NAMED_PROJECT: 6,
        GROUP_EVIDENCE_STRUCTURED_SERIES: 7,
        GROUP_EVIDENCE_NEEDS_DECISION: 8,
        GROUP_EVIDENCE_BROAD_ANCHOR: 9,
    }.get(evidence, 99)


def _anchor_decision_sort_rank(decision: str) -> int:
    return {
        ANCHOR_DECISION_SUGGESTED: 0,
        ANCHOR_DECISION_NEEDS_DECISION: 1,
        ANCHOR_DECISION_IGNORED: 2,
    }.get(decision, 99)


def _unique_sorted_files(files: list[FileMetadata]) -> list[FileMetadata]:
    by_path = {file.relative_path.as_posix(): file for file in files}
    return [by_path[path] for path in sorted(by_path)]


def _find_named_anchor_groups(
    files: list[FileMetadata],
    min_group_size: int,
) -> list[ProjectGroup]:
    anchor_to_files: dict[str, list[FileMetadata]] = {}
    file_to_anchors: dict[Path, set[str]] = {}
    anchor_display_names: dict[str, str] = {}

    for file in files:
        anchors = _named_anchor_candidates(file)
        file_to_anchors[file.relative_path] = {anchor for anchor, _display in anchors}
        for anchor, display_name in anchors:
            anchor_to_files.setdefault(anchor, []).append(file)
            anchor_display_names.setdefault(anchor, display_name)

    valid_anchors = {
        anchor
        for anchor, anchor_files in anchor_to_files.items()
        if len(anchor_files) >= min_group_size
    }
    assigned_by_anchor: dict[str, list[FileMetadata]] = {}
    for file in files:
        candidate_anchors = file_to_anchors[file.relative_path] & valid_anchors
        if not candidate_anchors:
            continue
        chosen_anchor = sorted(
            candidate_anchors,
            key=lambda anchor: (-len(anchor_to_files[anchor]), -len(anchor), anchor),
        )[0]
        assigned_by_anchor.setdefault(chosen_anchor, []).append(file)

    groups: list[ProjectGroup] = []
    for anchor, group_files in sorted(assigned_by_anchor.items()):
        if len(group_files) < min_group_size:
            continue
        display_name = anchor_display_names[anchor]
        groups.append(
            ProjectGroup(
                group_name=display_name,
                files=_sort_files(group_files),
                reason=f"files share strong filename anchor {anchor}; evidence {GROUP_EVIDENCE_NAMED_PROJECT}",
                confidence=80,
            )
        )
    return groups


def _named_anchor_candidates(file: FileMetadata) -> list[tuple[str, str]]:
    stem = file.relative_path.stem
    raw_tokens = [
        token
        for token in re.split(r"[^A-Za-z0-9]+", stem)
        if token
    ]
    normalized_tokens = [normalize_token(token) for token in raw_tokens]
    candidates: list[tuple[str, str]] = []
    if not normalized_tokens:
        return candidates

    first = normalized_tokens[0]
    if _is_allowed_named_anchor(first):
        candidates.append((first, _display_anchor(raw_tokens[0])))

    if len(normalized_tokens) >= 2 and re.search(r"[_-]", stem):
        first_two = normalized_tokens[:2]
        if all(_is_allowed_named_anchor(token) for token in first_two):
            key = "_".join(first_two)
            display = "_".join(_display_anchor(token) for token in raw_tokens[:2])
            candidates.append((key, display))

    return candidates


def _is_allowed_named_anchor(token: str) -> bool:
    return len(token) > 1 and token not in WEAK_GROUP_TOKENS


def _display_anchor(token: str) -> str:
    if any(character.isupper() for character in token[1:]):
        return token
    return token.capitalize()


def _all_filename_tokens(file: FileMetadata) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", file.relative_path.stem.lower())
        if token
    }


def _is_under_folder(relative_path: Path, folder_name: str) -> bool:
    return bool(relative_path.parts) and relative_path.parts[0] == folder_name


def _sort_files(files: list[FileMetadata]) -> list[FileMetadata]:
    return sorted(files, key=lambda file: file.relative_path.as_posix())


def _safe_group_name(group_name: str) -> str:
    name = group_name.replace("/", "-").replace("\\", "-").strip().replace(" ", "_")
    sanitized = "".join(
        character
        for character in name
        if character.isalnum() or character in {"_", "-"}
    )
    return sanitized or "group"


def _avoid_destination_collision(
    destination: Path,
    file: FileMetadata,
    used_destinations: set[Path],
) -> Path:
    if destination not in used_destinations:
        return destination

    prefixed_destination = destination.with_name(
        f"{_parent_prefix(file.relative_path)}_{file.name}"
    )
    if prefixed_destination not in used_destinations:
        return prefixed_destination

    counter = 2
    while True:
        candidate = destination.with_name(
            f"{prefixed_destination.stem}_{counter}{destination.suffix}"
        )
        if candidate not in used_destinations:
            return candidate
        counter += 1


def _parent_prefix(relative_path: Path) -> str:
    parent = relative_path.parent.as_posix()
    if parent in {"", "."}:
        return "root"
    prefix = parent.replace("/", "_").replace("\\", "_")
    sanitized = "".join(
        character
        for character in prefix
        if character.isalnum() or character in {"_", "-"}
    )
    return sanitized or "root"
