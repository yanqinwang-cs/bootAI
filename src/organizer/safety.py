from pathlib import Path


def validate_under_root(path: Path, root: Path) -> Path:
    resolved_path = path.resolve()
    resolved_root = root.resolve()

    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"{resolved_path} is outside root {resolved_root}")

    return resolved_path
