from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from organizer.application.review_service import create_review_session_from_scan_result
from organizer.application.view_models import ReviewApplicationSession
from organizer.web.scan_jobs import ScanJobSnapshot


@dataclass(frozen=True)
class ReviewExplorerSnapshot:
    status: str
    generation_id: str | None
    session: ReviewApplicationSession | None = None
    warnings: tuple[str, ...] = ()
    error_message: str | None = None


class ReviewExplorerStore:
    """Root-bound cache of read-only rows for the latest completed scan."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._lock = Lock()
        self._generation_id: str | None = None
        self._session: ReviewApplicationSession | None = None
        self._error_message: str | None = None

    def snapshot(self, scan: ScanJobSnapshot) -> ReviewExplorerSnapshot:
        with self._lock:
            if (
                scan.status != "completed"
                or scan.job_id is None
                or scan.result is None
            ):
                self._generation_id = scan.job_id
                self._session = None
                self._error_message = None
                return ReviewExplorerSnapshot(
                    status=scan.status,
                    generation_id=scan.job_id,
                    warnings=tuple(scan.result.warnings) if scan.result else (),
                    error_message=scan.error_message,
                )

            if self._generation_id != scan.job_id:
                self._generation_id = scan.job_id
                self._session = None
                self._error_message = None
                try:
                    self._session = create_review_session_from_scan_result(
                        scan.result
                    )
                except (OSError, UnicodeError, ValueError):
                    self._error_message = (
                        "Review findings are unavailable for this scan. "
                        "Return to the dashboard and try scanning again."
                    )

            return ReviewExplorerSnapshot(
                status="completed" if self._session is not None else "failed",
                generation_id=scan.job_id,
                session=self._session,
                warnings=tuple(scan.result.warnings),
                error_message=self._error_message,
            )
