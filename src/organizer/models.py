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
