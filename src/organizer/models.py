from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileMetadata:
    path: Path
    relative_path: Path
    name: str
    extension: str
    size_bytes: int
    modified_time: float
    is_dir: bool


@dataclass(frozen=True)
class DuplicateGroup:
    sha256: str
    size_bytes: int
    files: list[FileMetadata]


@dataclass(frozen=True)
class MovePlanItem:
    source: Path
    destination: Path
    reason: str
    confidence: int
    operation: str
    overwrite_risk: bool
