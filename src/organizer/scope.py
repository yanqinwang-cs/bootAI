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


def is_allowed_organization_file(
    metadata: FileMetadata,
    all_metadata: list[FileMetadata],
) -> bool:
    extension = metadata.extension.lower()
    if metadata.is_dir or metadata.path.is_symlink() or not metadata.path.is_file():
        return False
    if is_protected_or_project_context(metadata, all_metadata):
        return False
    if extension in EXCLUDED_ORGANIZATION_EXTENSIONS:
        return False
    if extension in {".html", ".htm"}:
        return is_standalone_html_document(metadata, all_metadata)
    return extension in DEFAULT_ORGANIZATION_EXTENSIONS


def is_standalone_html_document(
    metadata: FileMetadata,
    all_metadata: list[FileMetadata],
) -> bool:
    if metadata.extension.lower() not in {".html", ".htm"}:
        return False
    if is_protected_or_project_context(metadata, all_metadata):
        return False
    return not _has_web_project_context(metadata, all_metadata)


def is_orphan_code_candidate(
    metadata: FileMetadata,
    all_metadata: list[FileMetadata],
) -> bool:
    if metadata.extension.lower() not in ORPHAN_CODE_EXTENSIONS:
        return False
    if metadata.is_dir or metadata.path.is_symlink() or not metadata.path.is_file():
        return False
    return not is_protected_or_project_context(metadata, all_metadata)


def is_protected_or_project_context(
    metadata: FileMetadata,
    all_metadata: list[FileMetadata],
) -> bool:
    parts = metadata.relative_path.parts
    if not parts:
        return False
    if parts[0] in PROTECTED_ROOT_NAMES:
        return True
    if _has_protected_path_part(parts):
        return True
    marker_dirs = _marker_directories(all_metadata, PROJECT_MARKER_NAMES)
    file_parent = metadata.relative_path.parent
    return any(_is_same_or_under(file_parent, marker_dir) for marker_dir in marker_dirs)


def _has_web_project_context(
    metadata: FileMetadata,
    all_metadata: list[FileMetadata],
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


def _marker_directories(
    all_metadata: list[FileMetadata],
    marker_names: set[str],
) -> set[Path]:
    return {
        metadata.relative_path.parent
        for metadata in all_metadata
        if metadata.name in marker_names
    }


def _prefixed_marker_directories(
    all_metadata: list[FileMetadata],
    marker_prefixes: set[str],
) -> set[Path]:
    return {
        metadata.relative_path.parent
        for metadata in all_metadata
        if any(metadata.name.startswith(prefix) for prefix in marker_prefixes)
    }


def _named_directory_paths(
    all_metadata: list[FileMetadata],
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
