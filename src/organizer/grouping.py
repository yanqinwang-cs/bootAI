import re
from pathlib import Path

from organizer.models import (
    FileMetadata,
    MovePlanItem,
    OrganizationSuggestion,
    ProjectGroup,
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
COURSE_CODE_PATTERN = re.compile(r"[A-Za-z]{2,4}\d{4}[A-Za-z]?")
PAPER_TOKENS = {"paper", "article", "journal", "reading", "reference"}
RESULT_TOKENS = {"result", "results", "output", "experiment", "eval", "evaluation"}
CODE_EXTENSIONS = {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".html", ".css", ".ipynb"}
DATASET_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".json", ".parquet"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".rar", ".7z"}
DOCUMENT_EXTENSIONS = {".doc", ".docx", ".odt", ".pages"}


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


def find_project_groups(
    files: list[FileMetadata],
    review_folder_name: str = "AI_Review",
    min_group_size: int = 2,
) -> list[ProjectGroup]:
    eligible_files = _eligible_files(files, review_folder_name)
    assigned_paths: set[Path] = set()
    groups: list[ProjectGroup] = []

    course_groups: dict[str, list[FileMetadata]] = {}
    for file in eligible_files:
        course_code = extract_course_code(file)
        if course_code is not None:
            course_groups.setdefault(course_code, []).append(file)

    for course_code, group_files in sorted(course_groups.items()):
        if len(group_files) < min_group_size:
            continue
        sorted_files = _sort_files(group_files)
        groups.append(
            ProjectGroup(
                group_name=course_code,
                files=sorted_files,
                reason=f"files share course/module code {course_code}",
                confidence=90,
            )
        )
        assigned_paths.update(file.relative_path for file in sorted_files)

    remaining_files = [
        file for file in eligible_files if file.relative_path not in assigned_paths
    ]
    token_groups = _find_token_groups(remaining_files, min_group_size)
    groups.extend(token_groups)

    return sorted(groups, key=lambda group: (-group.confidence, group.group_name))


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
            subfolder = infer_subfolder(file)
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


def _find_token_groups(
    files: list[FileMetadata],
    min_group_size: int,
) -> list[ProjectGroup]:
    token_to_files: dict[str, list[FileMetadata]] = {}
    file_to_tokens: dict[Path, set[str]] = {}

    for file in files:
        tokens = extract_filename_tokens(file)
        file_to_tokens[file.relative_path] = tokens
        for token in tokens:
            token_to_files.setdefault(token, []).append(file)

    valid_tokens = {
        token
        for token, token_files in token_to_files.items()
        if len(token_files) >= min_group_size
    }
    assigned_by_token: dict[str, list[FileMetadata]] = {}
    for file in files:
        candidate_tokens = file_to_tokens[file.relative_path] & valid_tokens
        if not candidate_tokens:
            continue
        chosen_token = sorted(
            candidate_tokens,
            key=lambda token: (-len(token_to_files[token]), -len(token), token),
        )[0]
        assigned_by_token.setdefault(chosen_token, []).append(file)

    groups: list[ProjectGroup] = []
    for token, group_files in sorted(assigned_by_token.items()):
        if len(group_files) < min_group_size:
            continue
        groups.append(
            ProjectGroup(
                group_name=token.capitalize(),
                files=_sort_files(group_files),
                reason=f"files share filename token {token}",
                confidence=70,
            )
        )
    return groups


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
