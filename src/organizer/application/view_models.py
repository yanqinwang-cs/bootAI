from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from organizer.models import ReviewedPlanItem
from organizer.review_session import ReviewViewState
from organizer.review_state import ReviewState


@dataclass(frozen=True)
class ScanSummary:
    file_count: int
    total_bytes: int
    duplicate_group_count: int
    potential_duplicate_bytes: int
    review_candidate_count: int
    organization_suggestion_count: int


@dataclass(frozen=True)
class ScanApplicationResult:
    root: Path
    report: dict[str, Any]
    summary: ScanSummary
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ReviewApplicationSession:
    root: Path
    items: tuple[ReviewedPlanItem, ...]
    view_state: ReviewViewState
    source_path: Path | None
    saved_plan_path: Path | None
    review_state: ReviewState | None
    persist_review_state: bool
    review_state_ignored: bool
    saved_decisions: tuple[tuple[str, str], ...]

    @property
    def dirty(self) -> bool:
        current = tuple(sorted((item.id, item.decision) for item in self.items))
        return current != self.saved_decisions


@dataclass(frozen=True)
class ReviewDecisionChangeResult:
    session: ReviewApplicationSession
    decision: str
    changed_ids: tuple[str, ...]
    idempotent_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReviewSaveResult:
    session: ReviewApplicationSession
    reviewed_plan_path: Path
    review_state_path: Path | None


@dataclass(frozen=True)
class ArtifactSummary:
    artifact_type: str
    relative_path: str
    size_bytes: int
    modified_time: float


@dataclass(frozen=True)
class ArtifactLoadResult:
    summary: ArtifactSummary
    payload: object
