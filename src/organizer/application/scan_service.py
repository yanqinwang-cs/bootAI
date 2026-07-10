from __future__ import annotations

from pathlib import Path
from typing import Any

from organizer.application.view_models import ScanApplicationResult, ScanSummary
from organizer.ollama_client import OllamaClient
from organizer.reports import build_scan_report


def scan_root(
    root: Path,
    max_depth: int | None = None,
    *,
    refine_groups: bool = False,
    llm_client: OllamaClient | None = None,
) -> ScanApplicationResult:
    report = build_scan_report(
        root,
        max_depth=max_depth,
        refine_groups=refine_groups,
        llm_client=llm_client,
    )
    resolved_root = root.resolve()
    summary_data = _mapping(report.get("summary"), "report summary")
    warnings = _string_tuple(report.get("warnings"), "report warnings")
    duplicates = _list(report.get("duplicates"), "report duplicates")

    return ScanApplicationResult(
        root=resolved_root,
        report=report,
        summary=ScanSummary(
            file_count=_non_negative_int(summary_data.get("file_count"), "file_count"),
            total_bytes=_non_negative_int(summary_data.get("total_bytes"), "total_bytes"),
            duplicate_group_count=_non_negative_int(
                summary_data.get("duplicate_group_count"),
                "duplicate_group_count",
            ),
            potential_duplicate_bytes=_potential_duplicate_bytes(duplicates),
            review_candidate_count=_non_negative_int(
                summary_data.get("review_candidate_count"),
                "review_candidate_count",
            ),
            organization_suggestion_count=_non_negative_int(
                summary_data.get("organization_suggestion_count"),
                "organization_suggestion_count",
            ),
        ),
        warnings=warnings,
    )


def _potential_duplicate_bytes(duplicates: list[object]) -> int:
    total = 0
    for index, value in enumerate(duplicates, start=1):
        group = _mapping(value, f"duplicate group {index}")
        size_bytes = _non_negative_int(
            group.get("size_bytes"),
            f"duplicate group {index} size_bytes",
        )
        files = _list(group.get("files"), f"duplicate group {index} files")
        total += size_bytes * max(len(files) - 1, 0)
    return total


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    values = _list(value, label)
    if not all(isinstance(item, str) for item in values):
        raise ValueError(f"{label} must contain strings")
    return tuple(values)


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value
