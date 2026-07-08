from pathlib import Path

from organizer.models import FileMetadata
from organizer.safety import validate_under_root


def scan_directory(root: Path, max_depth: int | None = None) -> list[FileMetadata]:
    resolved_root = root.resolve()

    if not resolved_root.exists():
        raise ValueError(f"{resolved_root} does not exist")
    if not resolved_root.is_dir():
        raise ValueError(f"{resolved_root} is not a directory")
    if max_depth is not None and max_depth < 0:
        raise ValueError("max_depth must be non-negative")

    validate_under_root(resolved_root, resolved_root)

    results: list[FileMetadata] = []
    _scan_path(resolved_root, resolved_root, results, max_depth)
    return sorted(results, key=lambda metadata: metadata.relative_path.as_posix())


def _scan_path(
    path: Path,
    root: Path,
    results: list[FileMetadata],
    max_depth: int | None,
) -> None:
    try:
        resolved_path = validate_under_root(path, root)
    except ValueError:
        return

    try:
        stat_result = resolved_path.stat()
    except FileNotFoundError:
        return

    relative_path = resolved_path.relative_to(root)
    is_dir = resolved_path.is_dir()
    results.append(
        FileMetadata(
            path=resolved_path,
            relative_path=relative_path,
            name=resolved_path.name,
            extension=resolved_path.suffix,
            size_bytes=stat_result.st_size,
            modified_time=stat_result.st_mtime,
            is_dir=is_dir,
        )
    )

    if not is_dir:
        return

    depth = len(relative_path.parts)
    if max_depth is not None and depth >= max_depth:
        return

    for child in sorted(resolved_path.iterdir(), key=lambda item: item.name):
        if child.is_symlink():
            if not child.exists():
                continue
            try:
                validate_under_root(child, root)
            except ValueError:
                continue
        _scan_path(child, root, results, max_depth)
