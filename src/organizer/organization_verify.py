from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any

from organizer.reports import validate_report_output_path
from organizer.safety import validate_under_root

APPLY_RESULT_SCHEMA_VERSION = 1
APPLY_RESULT_SOURCE = "bootAI Stage 10.9 organization review apply result"
VERIFICATION_SCHEMA_VERSION = 1
VERIFICATION_SOURCE = "bootAI Stage 10.10 organization apply verification"
DEFAULT_VERIFICATION_PATH = (
    Path("AI_Review")
    / "reviews"
    / "organization_review_apply_verification.json"
)


@dataclass(frozen=True)
class OrganizationApplyVerificationOutcome:
    result_path: Path
    status: str
    passed: bool
    applied_count: int
    mismatch_count: int


class VerificationInputError(ValueError):
    pass


def verify_organization_apply(
    apply_result_path: Path,
    root: Path,
) -> OrganizationApplyVerificationOutcome:
    resolved_root = root.resolve()
    if not resolved_root.is_dir():
        raise ValueError(f"scan root is not a directory: {root}")

    resolved_apply_result = _resolve_input_file(apply_result_path, resolved_root)
    output_path = _next_verification_path(resolved_root)
    validate_report_output_path(output_path, resolved_root)

    try:
        apply_result = _load_json_object(resolved_apply_result, "apply result")
        validated = _validate_apply_result(apply_result, resolved_root)
        report = _verify_validated_result(
            validated,
            resolved_apply_result,
            resolved_root,
        )
    except VerificationInputError as error:
        report = _base_report(resolved_apply_result, resolved_root)
        report["status"] = "invalid_input"
        report["mismatches"] = [str(error)]
        report["checks"] = [
            {
                "name": "input_validation",
                "passed": False,
                "detail": str(error),
            }
        ]

    _write_verification(output_path, report)
    return OrganizationApplyVerificationOutcome(
        result_path=output_path,
        status=str(report["status"]),
        passed=bool(report["passed"]),
        applied_count=int(report["applied_count"]),
        mismatch_count=len(report["mismatches"]),
    )


def _validate_apply_result(data: dict[str, Any], root: Path) -> dict[str, Any]:
    required = {
        "schema_version",
        "source",
        "generated_at",
        "review_file",
        "confirmation",
        "approved_count",
        "applied_count",
        "skipped_count",
        "failed_count",
        "undo_log_path",
        "applied",
        "skipped",
        "failed",
        "warnings",
    }
    if set(data) != required:
        raise VerificationInputError("apply result fields do not match schema version 1")
    if data["schema_version"] != APPLY_RESULT_SCHEMA_VERSION:
        raise VerificationInputError("unsupported apply result schema version")
    if data["source"] != APPLY_RESULT_SOURCE:
        raise VerificationInputError("unexpected apply result source")
    if not isinstance(data["generated_at"], str) or not data["generated_at"]:
        raise VerificationInputError("apply result generated_at must be a non-empty string")
    try:
        datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise VerificationInputError("apply result generated_at must be an ISO timestamp") from error
    if data["confirmation"] != "APPLY ORGANIZATION REVIEW":
        raise VerificationInputError("unexpected apply result confirmation")
    _relative_path_value(data["review_file"], root, "review_file")

    for field in ("approved_count", "applied_count", "skipped_count", "failed_count"):
        value = data[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise VerificationInputError(f"apply result {field} must be a non-negative integer")
    for field in ("applied", "skipped", "failed", "warnings"):
        if not isinstance(data[field], list):
            raise VerificationInputError(f"apply result {field} must be a list")
    if not all(isinstance(item, str) for item in data["warnings"]):
        raise VerificationInputError("apply result warnings must contain strings")
    if data["applied_count"] != len(data["applied"]):
        raise VerificationInputError("applied_count does not match applied entries")
    if data["skipped_count"] != len(data["skipped"]):
        raise VerificationInputError("skipped_count does not match skipped entries")
    if data["failed_count"] != len(data["failed"]):
        raise VerificationInputError("failed_count does not match failed entries")

    applied = [_validate_result_item(item, root, failed=False) for item in data["applied"]]
    for item in data["failed"]:
        _validate_result_item(item, root, failed=True)
    for item in data["skipped"]:
        _validate_skipped_item(item)
    approved_skipped_count = sum(
        1 for item in data["skipped"] if item["decision"] == "approve"
    )
    expected_approved_count = (
        data["applied_count"] + data["failed_count"] + approved_skipped_count
    )
    if data["approved_count"] != expected_approved_count:
        raise VerificationInputError(
            "approved_count does not match applied, failed, and approved skipped entries"
        )

    undo_log_path = data["undo_log_path"]
    if applied and not isinstance(undo_log_path, str):
        raise VerificationInputError("undo_log_path is required when applied rows exist")
    if undo_log_path is not None and not isinstance(undo_log_path, str):
        raise VerificationInputError("undo_log_path must be a relative string or null")

    return {**data, "applied": applied}


def _validate_result_item(
    item: object,
    root: Path,
    *,
    failed: bool,
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise VerificationInputError("apply result item must be an object")
    required = {"review_id", "source", "destination", "anchor", "risk_level"}
    if failed:
        required.add("message")
    if set(item) != required:
        raise VerificationInputError("apply result item fields do not match schema")
    for field in ("review_id", "anchor", "risk_level"):
        if not isinstance(item[field], str) or not item[field]:
            raise VerificationInputError(f"apply result item {field} must be a non-empty string")
    if re.fullmatch(r"org-[0-9]{6}", item["review_id"]) is None:
        raise VerificationInputError("apply result review_id has an invalid format")
    if item["risk_level"] not in {"low", "medium", "high"}:
        raise VerificationInputError("apply result risk_level is invalid")
    if failed and not isinstance(item["message"], str):
        raise VerificationInputError("failed item message must be a string")
    source = _relative_path_value(item["source"], root, "source")
    destination = _relative_path_value(item["destination"], root, "destination")
    return {**item, "source": source, "destination": destination}


def _validate_skipped_item(item: object) -> None:
    if not isinstance(item, dict) or set(item) != {"review_id", "decision", "reason"}:
        raise VerificationInputError("skipped item fields do not match schema")
    if not all(isinstance(item[field], str) and item[field] for field in item):
        raise VerificationInputError("skipped item fields must be non-empty strings")


def _verify_validated_result(
    data: dict[str, Any],
    apply_result_path: Path,
    root: Path,
) -> dict[str, Any]:
    report = _base_report(apply_result_path, root)
    applied = data["applied"]
    report["applied_count"] = len(applied)
    mismatches: list[str] = []
    checks: list[dict[str, object]] = []

    _record_duplicate_conflicts(applied, mismatches)
    verified_destinations = 0
    verified_missing_sources = 0
    for item in applied:
        source = root / item["source"]
        destination = root / item["destination"]
        if not os.path.lexists(source):
            verified_missing_sources += 1
        else:
            mismatches.append(f"source still exists: {item['source']}")
        if destination.is_symlink():
            mismatches.append(f"destination is a symlink: {item['destination']}")
        elif destination.is_file():
            verified_destinations += 1
        else:
            mismatches.append(
                f"destination is missing or not a regular file: {item['destination']}"
            )

    report["verified_destination_count"] = verified_destinations
    report["verified_missing_source_count"] = verified_missing_sources
    checks.append(
        _check(
            "filesystem_state",
            verified_destinations == len(applied)
            and verified_missing_sources == len(applied),
            f"verified {verified_destinations} destination(s) and "
            f"{verified_missing_sources} absent source(s)",
        )
    )

    if applied:
        undo_path_text = data["undo_log_path"]
        assert isinstance(undo_path_text, str)
        operation_log_path = _resolve_referenced_file(undo_path_text, root)
        report["operation_log_file"] = operation_log_path.relative_to(root).as_posix()
        operation_log = _load_json_object(operation_log_path, "operation log")
        successful_pairs, log_warnings, log_mismatches = _validate_operation_log(
            operation_log,
            root,
        )
        report["warnings"].extend(log_warnings)
        mismatches.extend(log_mismatches)

        applied_pairs = {(item["source"], item["destination"]) for item in applied}
        only_result = sorted(applied_pairs - successful_pairs)
        only_log = sorted(successful_pairs - applied_pairs)
        mismatches.extend(
            f"applied pair missing from operation log: {source} -> {destination}"
            for source, destination in only_result
        )
        mismatches.extend(
            f"successful operation missing from apply result: {source} -> {destination}"
            for source, destination in only_log
        )
        count_matches = len(successful_pairs) == len(applied)
        if not count_matches:
            mismatches.append(
                "successful operation count does not match applied_count: "
                f"{len(successful_pairs)} != {len(applied)}"
            )
        checks.append(
            _check(
                "operation_log_matches",
                not only_result and not only_log and count_matches and not log_mismatches,
                f"matched {len(successful_pairs)} successful operation(s)",
            )
        )
    else:
        checks.append(_check("operation_log_matches", True, "no applied rows to match"))
        report["warnings"].append("Apply result contains no applied rows.")

    report["checks"] = checks
    report["mismatches"] = sorted(set(mismatches))
    report["passed"] = not report["mismatches"]
    report["status"] = "passed" if report["passed"] else "mismatches"
    return report


def _validate_operation_log(
    data: dict[str, Any],
    root: Path,
) -> tuple[set[tuple[str, str]], list[str], list[str]]:
    if set(data) != {"operations"} or not isinstance(data["operations"], list):
        raise VerificationInputError("operation log must contain only an operations list")
    pairs: list[tuple[str, str]] = []
    warnings: list[str] = []
    mismatches: list[str] = []
    for operation in data["operations"]:
        if not isinstance(operation, dict) or set(operation) != {
            "source", "destination", "success", "message"
        }:
            raise VerificationInputError("operation log entry fields do not match schema")
        if not isinstance(operation["success"], bool):
            raise VerificationInputError("operation success must be a boolean")
        if not isinstance(operation["message"], str):
            raise VerificationInputError("operation message must be a string")
        source = _operation_path(operation["source"], root, "operation source")
        destination = _operation_path(
            operation["destination"], root, "operation destination"
        )
        if operation["success"]:
            pairs.append((source, destination))
        else:
            warnings.append(f"operation log contains failed move: {source} -> {destination}")

    for index, label in ((0, "source"), (1, "destination")):
        grouped: dict[str, int] = {}
        for pair in pairs:
            grouped[pair[index]] = grouped.get(pair[index], 0) + 1
        mismatches.extend(
            f"duplicate successful operation {label}: {path}"
            for path, count in sorted(grouped.items())
            if count > 1
        )
    return set(pairs), warnings, mismatches


def _record_duplicate_conflicts(
    applied: list[dict[str, Any]],
    mismatches: list[str],
) -> None:
    for field in ("source", "destination"):
        counts: dict[str, int] = {}
        for item in applied:
            value = str(item[field])
            counts[value] = counts.get(value, 0) + 1
        mismatches.extend(
            f"duplicate applied {field}: {path}"
            for path, count in sorted(counts.items())
            if count > 1
        )


def _base_report(apply_result_path: Path, root: Path) -> dict[str, Any]:
    return {
        "schema_version": VERIFICATION_SCHEMA_VERSION,
        "source": VERIFICATION_SOURCE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verification_root": ".",
        "apply_result_file": apply_result_path.relative_to(root).as_posix(),
        "operation_log_file": None,
        "status": "invalid_input",
        "passed": False,
        "applied_count": 0,
        "verified_destination_count": 0,
        "verified_missing_source_count": 0,
        "checks": [],
        "mismatches": [],
        "warnings": [],
    }


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationInputError(f"could not read {label}: {error}") from error
    if not isinstance(data, dict):
        raise VerificationInputError(f"{label} must contain a JSON object")
    return data


def _resolve_input_file(path: Path, root: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    if candidate.is_symlink():
        raise ValueError(f"verification input is a symlink: {path}")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"verification input does not exist: {path}") from error
    validate_under_root(resolved, root)
    if not resolved.is_file():
        raise ValueError(f"verification input is not a regular file: {path}")
    return resolved


def _resolve_referenced_file(path_text: str, root: Path) -> Path:
    relative = _relative_path(path_text, root, "undo_log_path")
    candidate = root / relative
    if candidate.is_symlink():
        raise VerificationInputError("operation log is a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise VerificationInputError("referenced operation log does not exist") from error
    validate_under_root(resolved, root)
    if not resolved.is_file():
        raise VerificationInputError("referenced operation log is not a regular file")
    return resolved


def _relative_path_value(value: object, root: Path, label: str) -> str:
    if not isinstance(value, str):
        raise VerificationInputError(f"{label} must be a relative string")
    return _relative_path(value, root, label)


def _relative_path(path_text: str, root: Path, label: str) -> str:
    if not path_text or "\\" in path_text:
        raise VerificationInputError(f"{label} must be a safe relative path")
    path = Path(path_text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise VerificationInputError(f"{label} must be a safe relative path")
    resolved = (root / path).resolve(strict=False)
    validate_under_root(resolved, root)
    return resolved.relative_to(root).as_posix()


def _operation_path(value: object, root: Path, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise VerificationInputError(f"{label} must be a non-empty string")
    path = Path(value)
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve(strict=False)
    validate_under_root(resolved, root)
    return resolved.relative_to(root).as_posix()


def _next_verification_path(root: Path) -> Path:
    base = root / DEFAULT_VERIFICATION_PATH
    if not os.path.lexists(base):
        return base
    for counter in range(1, 1000):
        candidate = base.with_name(f"{base.stem}_{counter}{base.suffix}")
        if not os.path.lexists(candidate):
            return candidate
    raise ValueError(f"could not find unused verification path for {base}")


def _write_verification(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2, sort_keys=True)
        file.write("\n")


def _check(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "passed": passed, "detail": detail}
