from collections.abc import Sequence
from pathlib import Path

from organizer.models import FileMetadata

DEFAULT_ORGANIZATION_EXTENSIONS = {
    ".pdf",
    ".md",
    ".markdown",
    ".txt",
    ".rtf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".html",
    ".htm",
}
ORPHAN_CODE_EXTENSIONS = {
    ".py",
    ".java",
    ".ipynb",
    ".c",
    ".cpp",
    ".js",
    ".ts",
    ".go",
    ".rs",
}
GENERATED_ASSET_EXTENSIONS = {
    ".css",
    ".js",
    ".map",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
}
GENERATED_ASSET_FILENAMES = {
    "saved_resource.html",
}
GENERATED_ASSET_DIRECTORY_SUFFIXES = {
    "_files",
}
PROJECT_OUTPUT_DIRECTORY_NAMES = {
    "archive_experiment_files",
    "experiment_outputs",
    "build",
    "dist",
}
CONTEXTUAL_PROJECT_OUTPUT_DIRECTORY_NAMES = {
    "resources",
    "src",
}
PROJECT_CONTEXT_DIRECTORY_HINTS = {
    "app",
    "application",
    "backend",
    "frontend",
    "package",
    "project",
    "repo",
    "repository",
    "site",
    "web",
}
EXCLUDED_ORGANIZATION_EXTENSIONS = {
    ".h",
    ".hpp",
    ".jsx",
    ".tsx",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".css",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mov",
    ".mp4",
    ".mp3",
    ".wav",
    ".zip",
    ".tar",
    ".gz",
    ".dmg",
    ".pkg",
    ".exe",
    ".bin",
}
PROTECTED_ROOT_NAMES = {"AI_Review", "Organized", "Protected_Workspaces"}
PROTECTED_DIRECTORY_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}
PROTECTED_DIRECTORY_SUFFIXES = {
    ".app",
    ".framework",
    ".bundle",
    ".plugin",
    ".kext",
    ".xcodeproj",
    ".xcworkspace",
}
PROJECT_MARKER_NAMES = {
    ".git",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "poetry.lock",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "Cargo.toml",
    "go.mod",
    "Makefile",
}
WEB_PROJECT_MARKER_NAMES = {
    "package.json",
    "tsconfig.json",
    "style.css",
    "styles.css",
    "app.js",
    "main.js",
    "index.js",
}
WEB_PROJECT_MARKER_PREFIXES = {
    "vite.config.",
    "webpack.config.",
    "next.config.",
}
WEB_PROJECT_DIRECTORY_NAMES = {
    "src",
    "assets",
    "static",
    "public",
    "node_modules",
}


def is_protected_context_path(relative_path: Path) -> bool:
    parts = relative_path.parts
    if not parts:
        return False
    if parts[0] in PROTECTED_ROOT_NAMES:
        return True
    return _has_protected_path_part(parts)


def is_project_context_path(
    relative_path: Path,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    marker_dirs = _marker_directories(all_metadata, PROJECT_MARKER_NAMES)
    file_parent = relative_path.parent
    return any(_is_same_or_under(file_parent, marker_dir) for marker_dir in marker_dirs)


def is_actionable_plan_eligible(
    metadata: FileMetadata,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    if metadata.is_dir or metadata.path.is_symlink() or not metadata.path.is_file():
        return False
    return is_actionable_source_path(metadata.relative_path, all_metadata)


def is_actionable_source_path(
    relative_path: Path,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    return (
        not is_protected_context_path(relative_path)
        and not is_project_context_path(relative_path, all_metadata)
        and not is_generated_or_project_output_context_path(relative_path, all_metadata)
    )


def is_actionable_destination_path(
    relative_path: Path,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    if relative_path.parts and relative_path.parts[0] in {"AI_Review", "Organized"}:
        return True
    return is_actionable_source_path(relative_path, all_metadata)


def is_generated_or_project_output_context_path(
    relative_path: Path,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    return (
        is_generated_asset_context_path(relative_path)
        or is_generated_asset_context(relative_path, all_metadata)
        or is_project_output_context_path(relative_path, all_metadata)
    )


def is_generated_asset_context_path(relative_path: Path) -> bool:
    parts = relative_path.parts
    lowered_parts = [part.lower() for part in parts]
    if any(part.endswith(tuple(GENERATED_ASSET_DIRECTORY_SUFFIXES)) for part in lowered_parts[:-1]):
        return True
    if relative_path.name.lower() in GENERATED_ASSET_FILENAMES:
        return True
    if _looks_like_generated_asset_name(relative_path):
        return True
    return False


def is_generated_asset_context(
    relative_path: Path,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    if is_generated_asset_context_path(relative_path):
        return True
    if relative_path.suffix.lower() not in GENERATED_ASSET_EXTENSIONS:
        return False
    parent = relative_path.parent
    siblings = [
        metadata
        for metadata in all_metadata
        if not metadata.is_dir and metadata.relative_path.parent == parent
    ]
    if len(siblings) < 3:
        return False
    generated_siblings = [
        metadata
        for metadata in siblings
        if (
            metadata.extension.lower() in GENERATED_ASSET_EXTENSIONS
            or metadata.name.lower() in GENERATED_ASSET_FILENAMES
            or _looks_like_generated_asset_name(metadata.relative_path)
        )
    ]
    return len(generated_siblings) / len(siblings) >= 0.6


def is_project_output_context_path(
    relative_path: Path,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    parts = relative_path.parts
    lowered_parts = [part.lower() for part in parts[:-1]]
    if any(part in PROJECT_OUTPUT_DIRECTORY_NAMES for part in lowered_parts):
        return True
    for index, part in enumerate(lowered_parts):
        if part not in CONTEXTUAL_PROJECT_OUTPUT_DIRECTORY_NAMES:
            continue
        parent_parts = lowered_parts[:index]
        if any(parent in PROJECT_CONTEXT_DIRECTORY_HINTS for parent in parent_parts):
            return True
        if is_project_context_path(relative_path, all_metadata):
            return True
    return False


def is_allowed_organization_file(
    metadata: FileMetadata,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    extension = metadata.extension.lower()
    if not is_actionable_plan_eligible(metadata, all_metadata):
        return False
    if extension in EXCLUDED_ORGANIZATION_EXTENSIONS:
        return False
    if extension in {".html", ".htm"}:
        return is_standalone_html_document(metadata, all_metadata)
    return extension in DEFAULT_ORGANIZATION_EXTENSIONS


def is_standalone_html_document(
    metadata: FileMetadata,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    if metadata.extension.lower() not in {".html", ".htm"}:
        return False
    if not is_actionable_plan_eligible(metadata, all_metadata):
        return False
    return not _has_web_project_context(metadata, all_metadata)


def is_orphan_code_candidate(
    metadata: FileMetadata,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    if metadata.extension.lower() not in ORPHAN_CODE_EXTENSIONS:
        return False
    return is_actionable_plan_eligible(metadata, all_metadata)


def is_protected_or_project_context(
    metadata: FileMetadata,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    return (
        is_protected_context_path(metadata.relative_path)
        or is_project_context_path(metadata.relative_path, all_metadata)
    )


def _has_web_project_context(
    metadata: FileMetadata,
    all_metadata: Sequence[FileMetadata],
) -> bool:
    marker_dirs = _marker_directories(all_metadata, WEB_PROJECT_MARKER_NAMES)
    marker_dirs.update(_prefixed_marker_directories(all_metadata, WEB_PROJECT_MARKER_PREFIXES))
    marker_dirs.update(_named_directory_paths(all_metadata, WEB_PROJECT_DIRECTORY_NAMES))
    file_parent = metadata.relative_path.parent
    return any(_is_same_or_under(file_parent, marker_dir) for marker_dir in marker_dirs)


def _has_protected_path_part(parts: tuple[str, ...]) -> bool:
    for part in parts[:-1]:
        if part in PROTECTED_DIRECTORY_NAMES:
            return True
        if any(part.endswith(suffix) for suffix in PROTECTED_DIRECTORY_SUFFIXES):
            return True
    return False


def _looks_like_generated_asset_name(relative_path: Path) -> bool:
    stem = relative_path.stem.lower()
    suffix = relative_path.suffix.lower()
    if suffix not in GENERATED_ASSET_EXTENSIONS:
        return False
    if ".min" in relative_path.name.lower():
        return True
    compact = stem.replace("-", "").replace("_", "").replace(".", "")
    return len(compact) >= 12 and all(character in "0123456789abcdef" for character in compact)


def _marker_directories(
    all_metadata: Sequence[FileMetadata],
    marker_names: set[str],
) -> set[Path]:
    return {
        metadata.relative_path.parent
        for metadata in all_metadata
        if metadata.name in marker_names
    }


def _prefixed_marker_directories(
    all_metadata: Sequence[FileMetadata],
    marker_prefixes: set[str],
) -> set[Path]:
    return {
        metadata.relative_path.parent
        for metadata in all_metadata
        if any(metadata.name.startswith(prefix) for prefix in marker_prefixes)
    }


def _named_directory_paths(
    all_metadata: Sequence[FileMetadata],
    directory_names: set[str],
) -> set[Path]:
    return {
        metadata.relative_path
        for metadata in all_metadata
        if metadata.is_dir and metadata.name in directory_names
    }


def _is_same_or_under(path: Path, possible_parent: Path) -> bool:
    normalized_path = _normalize_relative_path(path)
    normalized_parent = _normalize_relative_path(possible_parent)
    return normalized_path == normalized_parent or normalized_parent in normalized_path.parents


def _normalize_relative_path(path: Path) -> Path:
    return Path(".") if path.as_posix() in {"", "."} else path
