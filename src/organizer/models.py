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


@dataclass(frozen=True)
class MoveResult:
    source: Path
    destination: Path
    success: bool
    message: str


@dataclass(frozen=True)
class OperationLog:
    log_path: Path
    operations: list[MoveResult]


@dataclass(frozen=True)
class ReviewCandidate:
    file: FileMetadata
    category: str
    reason: str
    confidence: int


@dataclass(frozen=True)
class ProjectGroup:
    group_name: str
    files: list[FileMetadata]
    reason: str
    confidence: int


@dataclass(frozen=True)
class OrganizationSuggestion:
    group: ProjectGroup
    suggested_root: Path
    plan_items: list[MovePlanItem]


@dataclass(frozen=True)
class LLMRefinement:
    original_group_name: str
    folder_name: str
    confidence: int
    reason: str
    subfolders: dict[str, str]
    warnings: list[str]
