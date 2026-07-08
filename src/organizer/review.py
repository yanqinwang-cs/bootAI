import re
from pathlib import Path

from organizer.models import FileMetadata, MovePlanItem, ReviewCandidate

TEMPORARY_EXACT_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
TEMPORARY_SUFFIXES = {".tmp", ".temp", ".part", ".crdownload", ".swp", ".swo"}
INTENTIONAL_EMPTY_NAMES = {"__init__.py", ".gitkeep", ".keep"}
BACKUP_OR_COPY_TOKENS = {
    "copy",
    "backup",
    "bak",
    "old",
    "previous",
    "prev",
    "finalfinal",
    "duplicate",
    "duplicated",
}


def detect_review_candidates(
    files: list[FileMetadata],
    review_folder_name: str = "AI_Review",
) -> list[ReviewCandidate]:
    candidates: list[ReviewCandidate] = []

    for metadata in files:
        if metadata.is_dir or metadata.path.is_symlink() or not metadata.path.is_file():
            continue
        if _is_under_review_folder(metadata.relative_path, review_folder_name):
            continue

        candidate = _detect_candidate(metadata)
        if candidate is not None:
            candidates.append(candidate)

    return sorted(
        candidates,
        key=lambda candidate: candidate.file.relative_path.as_posix(),
    )


def build_review_candidate_plan(
    candidates: list[ReviewCandidate],
    root: Path,
    review_folder_name: str = "AI_Review",
) -> list[MovePlanItem]:
    plan_items: list[MovePlanItem] = []

    for candidate in sorted(
        candidates,
        key=lambda item: item.file.relative_path.as_posix(),
    ):
        destination = (
            root
            / review_folder_name
            / candidate.category
            / candidate.file.relative_path
        )
        plan_items.append(
            MovePlanItem(
                source=candidate.file.path,
                destination=destination,
                reason=candidate.reason,
                confidence=candidate.confidence,
                operation="dry-run move",
                overwrite_risk=destination.exists(),
            )
        )

    return plan_items


def _detect_candidate(metadata: FileMetadata) -> ReviewCandidate | None:
    if _is_temporary(metadata.name):
        return ReviewCandidate(
            file=metadata,
            category="temporary",
            reason="filename matches a temporary or system-artifact pattern",
            confidence=95,
        )
    if _is_empty_candidate(metadata):
        return ReviewCandidate(
            file=metadata,
            category="empty",
            reason="file is 0 bytes and is not a known intentional placeholder",
            confidence=80,
        )
    if _is_backup_or_copy(metadata.path.stem):
        return ReviewCandidate(
            file=metadata,
            category="backup_or_copy",
            reason="filename contains a backup/copy/version marker",
            confidence=70,
        )
    return None


def _is_under_review_folder(relative_path: Path, review_folder_name: str) -> bool:
    return bool(relative_path.parts) and relative_path.parts[0] == review_folder_name


def _is_temporary(name: str) -> bool:
    return (
        name in TEMPORARY_EXACT_NAMES
        or any(name.endswith(suffix) for suffix in TEMPORARY_SUFFIXES)
        or name.startswith("~")
        or name.startswith(".~")
        or name.startswith("~$")
        or name.endswith("~")
    )


def _is_empty_candidate(metadata: FileMetadata) -> bool:
    return metadata.size_bytes == 0 and metadata.name not in INTENTIONAL_EMPTY_NAMES


def _is_backup_or_copy(stem: str) -> bool:
    tokens = [
        token
        for token in re.split(r"[^a-z0-9]+", stem.lower())
        if token
    ]
    return any(token in BACKUP_OR_COPY_TOKENS for token in tokens)
