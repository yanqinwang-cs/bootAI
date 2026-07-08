from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil

from organizer.models import MovePlanItem, MoveResult, OperationLog


def apply_move_plan(
    plan_items: list[MovePlanItem],
    root: Path,
    log_dir_name: str = "operation_logs",
) -> OperationLog:
    resolved_root = root.resolve()
    validated_items = [
        _validate_plan_item(item, resolved_root) for item in plan_items
    ]

    operations: list[MoveResult] = []
    log_path = _next_log_path(resolved_root, log_dir_name, "operation_log")

    for item in validated_items:
        item.destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(item.source), str(item.destination))
        except Exception as error:
            operations.append(
                MoveResult(
                    source=item.source,
                    destination=item.destination,
                    success=False,
                    message=f"move failed: {error}",
                )
            )
            return _write_operation_log(log_path, operations)

        operations.append(
            MoveResult(
                source=item.source,
                destination=item.destination,
                success=True,
                message="moved",
            )
        )

    return _write_operation_log(log_path, operations)


def undo_operation_log(log_path: Path, root: Path) -> OperationLog:
    resolved_root = root.resolve()
    resolved_log_path = _validate_existing_path_under_root(log_path, resolved_root)

    with resolved_log_path.open("r", encoding="utf-8") as file:
        log_data = json.load(file)

    logged_results = _load_move_results(log_data)
    successful_results = [result for result in logged_results if result.success]

    for result in successful_results:
        _validate_path_under_root(result.source, resolved_root)
        _validate_path_under_root(result.destination, resolved_root)

    undo_results: list[MoveResult] = []
    result_log_path = _next_log_path(resolved_root, "operation_logs", "undo_result_log")

    for result in successful_results:
        if os.path.lexists(result.source):
            undo_results.append(
                MoveResult(
                    source=result.destination,
                    destination=result.source,
                    success=False,
                    message="original source path already exists",
                )
            )
            continue
        if result.destination.is_symlink() or not result.destination.is_file():
            undo_results.append(
                MoveResult(
                    source=result.destination,
                    destination=result.source,
                    success=False,
                    message="logged destination is not a regular file",
                )
            )
            continue

        _validate_destination_path(result.source, resolved_root)
        result.source.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(result.destination), str(result.source))
        except Exception as error:
            undo_results.append(
                MoveResult(
                    source=result.destination,
                    destination=result.source,
                    success=False,
                    message=f"undo failed: {error}",
                )
            )
            continue

        undo_results.append(
            MoveResult(
                source=result.destination,
                destination=result.source,
                success=True,
                message="restored",
            )
        )

    return _write_operation_log(result_log_path, undo_results)


def _validate_plan_item(item: MovePlanItem, root: Path) -> MovePlanItem:
    _validate_source_path(item.source, root)
    _validate_destination_path(item.destination, root)
    if os.path.lexists(item.destination):
        raise ValueError(f"destination already exists: {item.destination}")
    return item


def _validate_source_path(path: Path, root: Path) -> Path:
    if path.is_symlink():
        raise ValueError(f"source is a symlink: {path}")
    resolved_path = _validate_existing_path_under_root(path, root)
    if not path.exists():
        raise ValueError(f"source does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"source is not a regular file: {path}")
    return resolved_path


def _validate_existing_path_under_root(path: Path, root: Path) -> Path:
    resolved_path = path.resolve()
    if not _is_under_root(resolved_path, root):
        raise ValueError(f"path is outside root: {path}")
    return resolved_path


def _validate_path_under_root(path: Path, root: Path) -> Path:
    resolved_path = path.resolve(strict=False)
    if not _is_under_root(resolved_path, root):
        raise ValueError(f"path is outside root: {path}")
    return resolved_path


def _validate_destination_path(path: Path, root: Path) -> Path:
    resolved_path = _validate_path_under_root(path, root)
    existing_parent = _nearest_existing_parent(path.parent)
    resolved_parent = existing_parent.resolve()
    if not _is_under_root(resolved_parent, root):
        raise ValueError(f"destination parent is outside root: {path}")
    if not existing_parent.is_dir():
        raise ValueError(f"destination parent is not a directory: {existing_parent}")
    return resolved_path


def _nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current


def _is_under_root(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _next_log_path(root: Path, log_dir_name: str, prefix: str) -> Path:
    log_dir = root / "AI_Review" / log_dir_name
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = log_dir / f"{prefix}_{timestamp}.json"
    counter = 1
    while candidate.exists():
        candidate = log_dir / f"{prefix}_{timestamp}_{counter}.json"
        counter += 1
    return candidate


def _write_operation_log(log_path: Path, operations: list[MoveResult]) -> OperationLog:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_data = {
        "operations": [
            {
                "source": str(result.source),
                "destination": str(result.destination),
                "success": result.success,
                "message": result.message,
            }
            for result in operations
        ]
    }
    with log_path.open("w", encoding="utf-8") as file:
        json.dump(log_data, file, indent=2, sort_keys=True)
        file.write("\n")
    return OperationLog(log_path=log_path, operations=operations)


def _load_move_results(log_data: object) -> list[MoveResult]:
    if not isinstance(log_data, dict):
        raise ValueError("operation log must contain an object")
    operations = log_data.get("operations")
    if not isinstance(operations, list):
        raise ValueError("operation log must contain an operations list")

    results: list[MoveResult] = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError("operation entry must contain an object")
        results.append(
            MoveResult(
                source=Path(str(operation["source"])),
                destination=Path(str(operation["destination"])),
                success=bool(operation["success"]),
                message=str(operation["message"]),
            )
        )
    return results
