import hashlib
from pathlib import Path

from organizer.models import DuplicateGroup, FileMetadata


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path} is not a regular file")

    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def find_exact_duplicates(files: list[FileMetadata]) -> list[DuplicateGroup]:
    groups_by_hash: dict[str, list[FileMetadata]] = {}

    for metadata in files:
        if metadata.is_dir:
            continue
        try:
            sha256 = hash_file(metadata.path)
        except ValueError:
            continue
        groups_by_hash.setdefault(sha256, []).append(metadata)

    duplicate_groups: list[DuplicateGroup] = []
    for sha256, group_files in groups_by_hash.items():
        if len(group_files) < 2:
            continue
        sorted_files = sorted(
            group_files,
            key=lambda metadata: metadata.relative_path.as_posix(),
        )
        duplicate_groups.append(
            DuplicateGroup(
                sha256=sha256,
                size_bytes=sorted_files[0].size_bytes,
                files=sorted_files,
            )
        )

    return sorted(
        duplicate_groups,
        key=lambda group: (-group.size_bytes, group.sha256),
    )
