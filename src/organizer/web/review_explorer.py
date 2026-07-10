from __future__ import annotations

from dataclasses import dataclass
import hmac
from pathlib import Path
import secrets
from threading import Lock
from collections.abc import Callable

from organizer.application.review_service import (
    apply_current_page_decision,
    change_review_decisions,
    create_review_session_from_scan_result,
    get_review_item,
    preview_current_page_decision,
    save_review_session,
)
from organizer.application.view_models import (
    ReviewApplicationSession,
    ReviewDecisionChangeResult,
    ReviewSaveResult,
)
from organizer.review_session import PageDecisionPreview
from organizer.web.scan_jobs import (
    ScanJobController,
    ScanJobSnapshot,
)


class ReviewSessionUnavailable(RuntimeError):
    pass


class ReviewItemNotFound(ValueError):
    pass


class ReviewPreviewUnavailable(ValueError):
    pass


class ReviewConfirmationRejected(ValueError):
    pass


class UnsavedReviewChanges(RuntimeError):
    pass


SessionProjection = Callable[[ReviewApplicationSession], ReviewApplicationSession]


@dataclass(frozen=True)
class ReviewExplorerSnapshot:
    status: str
    generation_id: str | None
    session: ReviewApplicationSession | None = None
    warnings: tuple[str, ...] = ()
    error_message: str | None = None


@dataclass(frozen=True)
class PendingPageDecision:
    browser_session_id: str
    generation_id: str
    preview: PageDecisionPreview
    view_query: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PageDecisionPreviewResult:
    preview: PageDecisionPreview
    preview_token: str | None


@dataclass(frozen=True)
class PageDecisionConfirmationResult:
    change: ReviewDecisionChangeResult
    view_query: tuple[tuple[str, str], ...]


class ReviewExplorerStore:
    """Own the mutable web pointer to one immutable generation-bound session."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._lock = Lock()
        self._generation_id: str | None = None
        self._session: ReviewApplicationSession | None = None
        self._error_message: str | None = None
        self._pending_page_decisions: dict[str, PendingPageDecision] = {}

    def snapshot(self, scan: ScanJobSnapshot) -> ReviewExplorerSnapshot:
        with self._lock:
            return self._synchronize_locked(scan)

    def start_scan(self, controller: ScanJobController) -> ScanJobSnapshot:
        with self._lock:
            current = self._synchronize_locked(controller.snapshot())
            if current.session is not None and current.session.dirty:
                raise UnsavedReviewChanges(
                    "Save the reviewed plan before starting another scan."
                )
            started = controller.start()
            self._invalidate_locked(started.job_id)
            return started

    def change_decision(
        self,
        scan: ScanJobSnapshot,
        item_id: str,
        decision: str,
        *,
        project: SessionProjection,
    ) -> ReviewDecisionChangeResult:
        with self._lock:
            session = self._require_session_locked(scan)
            project(session)
            try:
                get_review_item(session, item_id)
                result = change_review_decisions(session, (item_id,), decision)
            except ValueError as error:
                raise ReviewItemNotFound(str(error)) from error
            self._session = result.session
            if result.changed_ids:
                self._pending_page_decisions.clear()
            return result

    def preview_page_decision(
        self,
        scan: ScanJobSnapshot,
        browser_session_id: str,
        decision: str,
        *,
        project: SessionProjection,
        view_query: tuple[tuple[str, str], ...],
    ) -> PageDecisionPreviewResult:
        with self._lock:
            session = self._require_session_locked(scan)
            projected = project(session)
            preview = preview_current_page_decision(projected, decision)
            self._drop_previews_for_session_locked(browser_session_id)
            if not preview.target_ids or not preview.change_ids:
                return PageDecisionPreviewResult(preview, None)
            token = secrets.token_urlsafe(32)
            self._pending_page_decisions[token] = PendingPageDecision(
                browser_session_id=browser_session_id,
                generation_id=self._generation_id or "",
                preview=preview,
                view_query=view_query,
            )
            return PageDecisionPreviewResult(preview, token)

    def confirm_page_decision(
        self,
        scan: ScanJobSnapshot,
        browser_session_id: str,
        preview_token: str,
        confirmation: str,
    ) -> PageDecisionConfirmationResult:
        with self._lock:
            session = self._require_session_locked(scan)
            pending = self._pending_page_decisions.get(preview_token)
            if pending is None:
                raise ReviewPreviewUnavailable(
                    "That current-page preview is no longer available."
                )
            if pending.browser_session_id != browser_session_id:
                raise ReviewPreviewUnavailable(
                    "That current-page preview is no longer available."
                )
            if pending.generation_id != self._generation_id:
                self._pending_page_decisions.pop(preview_token, None)
                raise ReviewPreviewUnavailable(
                    "That current-page preview belongs to an earlier scan."
                )

            self._pending_page_decisions.pop(preview_token, None)
            if not hmac.compare_digest(confirmation, pending.preview.confirmation):
                raise ReviewConfirmationRejected(
                    "The confirmation did not match. No decisions were changed."
                )

            change = apply_current_page_decision(session, pending.preview)
            self._session = change.session
            self._pending_page_decisions.clear()
            return PageDecisionConfirmationResult(change, pending.view_query)

    def save(
        self,
        scan: ScanJobSnapshot,
        *,
        project: SessionProjection,
    ) -> ReviewSaveResult:
        with self._lock:
            session = self._require_session_locked(scan)
            project(session)
            result = save_review_session(session)
            self._session = result.session
            self._pending_page_decisions.clear()
            return result

    def _synchronize_locked(
        self,
        scan: ScanJobSnapshot,
    ) -> ReviewExplorerSnapshot:
        if (
            scan.status != "completed"
            or scan.job_id is None
            or scan.result is None
        ):
            self._invalidate_locked(scan.job_id)
            return ReviewExplorerSnapshot(
                status=scan.status,
                generation_id=scan.job_id,
                warnings=tuple(scan.result.warnings) if scan.result else (),
                error_message=scan.error_message,
            )

        if self._generation_id != scan.job_id or (
            self._session is None and self._error_message is None
        ):
            self._invalidate_locked(scan.job_id)
            try:
                session = create_review_session_from_scan_result(scan.result)
                if session.root != self._root:
                    raise ValueError("review session root does not match web root")
                self._session = session
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

    def _require_session_locked(
        self,
        scan: ScanJobSnapshot,
    ) -> ReviewApplicationSession:
        snapshot = self._synchronize_locked(scan)
        if snapshot.status != "completed" or snapshot.session is None:
            raise ReviewSessionUnavailable(
                "No completed scan review session is available."
            )
        return snapshot.session

    def _invalidate_locked(self, generation_id: str | None) -> None:
        self._generation_id = generation_id
        self._session = None
        self._error_message = None
        self._pending_page_decisions.clear()

    def _drop_previews_for_session_locked(self, browser_session_id: str) -> None:
        self._pending_page_decisions = {
            token: pending
            for token, pending in self._pending_page_decisions.items()
            if pending.browser_session_id != browser_session_id
        }
