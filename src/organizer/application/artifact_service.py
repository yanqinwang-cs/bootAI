from __future__ import annotations

from pathlib import Path

from organizer.application.view_models import ArtifactLoadResult, ArtifactSummary
from organizer.reports import load_report
from organizer.review_session import load_reviewed_plan_items
from organizer.safety import validate_under_root

ARTIFACT_SCAN_REPORT = "scan_report"
ARTIFACT_REVIEWED_PLAN = "reviewed_plan"

_ARTIFACT_FOLDERS = {
    ARTIFACT_SCAN_REPORT: Path("AI_Review") / "reports",
    ARTIFACT_REVIEWED_PLAN: Path("AI_Review") / "review_sessions",
}


class InvalidArtifact(ValueError):
    pass


class UnsupportedArtifact(ValueError):
    pass


def list_artifacts(
    root: Path,
    artifact_type: str | None = None,
) -> tuple[ArtifactSummary, ...]:
    resolved_root = _validated_root(root)
    artifact_types = (
        tuple(_ARTIFACT_FOLDERS)
        if artifact_type is None
        else (_validated_artifact_type(artifact_type),)
    )

    summaries: list[ArtifactSummary] = []
    for current_type in artifact_types:
        folder = resolved_root / _ARTIFACT_FOLDERS[current_type]
        if not folder.exists():
            continue
        resolved_folder = validate_under_root(folder.resolve(), resolved_root)
        if not resolved_folder.is_dir():
            raise InvalidArtifact(f"artifact folder is not a directory: {folder}")
        for candidate in resolved_folder.glob("*.json"):
            if candidate.is_symlink() or not candidate.is_file():
                continue
            summaries.append(_artifact_summary(candidate, current_type, resolved_root))

    return tuple(
        sorted(
            summaries,
            key=lambda summary: (summary.artifact_type, summary.relative_path),
        )
    )


def load_artifact(
    root: Path,
    artifact_type: str,
    relative_path: str | Path,
) -> ArtifactLoadResult:
    resolved_root = _validated_root(root)
    validated_type = _validated_artifact_type(artifact_type)
    path = _validated_relative_path(relative_path)
    candidate = resolved_root / path

    if candidate.is_symlink():
        raise InvalidArtifact(f"artifact must not be a symlink: {path.as_posix()}")
    try:
        resolved_candidate = validate_under_root(
            candidate.resolve(strict=False),
            resolved_root,
        )
        allowed_folder = (
            resolved_root / _ARTIFACT_FOLDERS[validated_type]
        ).resolve(strict=False)
        validate_under_root(resolved_candidate, allowed_folder)
    except ValueError as error:
        raise InvalidArtifact(str(error)) from error

    if not candidate.exists():
        raise InvalidArtifact(f"artifact does not exist: {path.as_posix()}")
    if not candidate.is_file():
        raise InvalidArtifact(f"artifact is not a regular file: {path.as_posix()}")
    if candidate.suffix.lower() != ".json":
        raise InvalidArtifact(f"artifact must be a JSON file: {path.as_posix()}")

    try:
        if validated_type == ARTIFACT_SCAN_REPORT:
            payload: object = load_report(resolved_candidate, resolved_root)
        else:
            payload = tuple(
                load_reviewed_plan_items(resolved_candidate, resolved_root)
            )
    except (OSError, UnicodeError, ValueError) as error:
        raise InvalidArtifact(str(error)) from error

    return ArtifactLoadResult(
        summary=_artifact_summary(
            resolved_candidate,
            validated_type,
            resolved_root,
        ),
        payload=payload,
    )


def _validated_root(root: Path) -> Path:
    resolved_root = root.resolve()
    if not resolved_root.exists():
        raise InvalidArtifact(f"artifact root does not exist: {root}")
    if not resolved_root.is_dir():
        raise InvalidArtifact(f"artifact root is not a directory: {root}")
    return validate_under_root(resolved_root, resolved_root)


def _validated_artifact_type(artifact_type: str) -> str:
    if artifact_type not in _ARTIFACT_FOLDERS:
        supported = ", ".join(sorted(_ARTIFACT_FOLDERS))
        raise UnsupportedArtifact(
            f"unsupported artifact type: {artifact_type}; supported types: {supported}"
        )
    return artifact_type


def _validated_relative_path(value: str | Path) -> Path:
    text = str(value)
    if not text or "\\" in text:
        raise InvalidArtifact("artifact path must be a safe relative path")
    path = Path(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise InvalidArtifact("artifact path must be a safe relative path")
    return path


def _artifact_summary(
    path: Path,
    artifact_type: str,
    root: Path,
) -> ArtifactSummary:
    stat = path.stat()
    relative_path = validate_under_root(path.resolve(), root).relative_to(root)
    return ArtifactSummary(
        artifact_type=artifact_type,
        relative_path=relative_path.as_posix(),
        size_bytes=stat.st_size,
        modified_time=stat.st_mtime,
    )
