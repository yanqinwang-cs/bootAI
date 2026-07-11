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
    create_fresh_web_review_session_from_scan_result,
    dirty_review_modules,
    get_review_item,
    preview_current_page_decision,
    review_module_category,
    save_review_module,
    save_review_session,
)
from organizer.application.view_models import (
    ModuleReviewSaveResult,
    ReviewApplicationSession,
    ReviewDecisionChangeResult,
    ReviewModule,
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
    def __init__(self, modules: tuple[ReviewModule, ...]) -> None:
        super().__init__("review session has unsaved module choices")
        self.modules = modules


SessionProjection = Callable[[ReviewApplicationSession], ReviewApplicationSession]
SessionItemValidator = Callable[
    [ReviewApplicationSession, str, "ModuleQueueSnapshot"],
    bool,
]


@dataclass(frozen=True)
class ModuleQueueSnapshot:
    module: ReviewModule
    handled_ids: tuple[str, ...] = ()
    deferred_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewExplorerSnapshot:
    status: str
    generation_id: str | None
    session: ReviewApplicationSession | None = None
    warnings: tuple[str, ...] = ()
    error_message: str | None = None
    module_queues: tuple[ModuleQueueSnapshot, ...] = ()

    def queue_for(self, module: ReviewModule) -> ModuleQueueSnapshot:
        for queue in self.module_queues:
            if queue.module == module:
                return queue
        return ModuleQueueSnapshot(module)


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
        self._module_handled: dict[ReviewModule, set[str]] = {
            module: set() for module in ReviewModule
        }
        self._module_deferred: dict[ReviewModule, set[str]] = {
            module: set() for module in ReviewModule
        }

    def snapshot(self, scan: ScanJobSnapshot) -> ReviewExplorerSnapshot:
        with self._lock:
            return self._synchronize_locked(scan)

    def start_scan(self, controller: ScanJobController) -> ScanJobSnapshot:
        with self._lock:
            current = self._synchronize_locked(controller.snapshot())
            if current.session is not None and current.session.dirty:
                raise UnsavedReviewChanges(dirty_review_modules(current.session))
            started = controller.start()
            self._invalidate_locked(started.job_id)
            return started

    def change_decision(
        self,
        scan: ScanJobSnapshot,
        item_id: str,
        decision: str,
        *,
        expected_category: str | None = None,
        item_validator: SessionItemValidator | None = None,
        queue_module: ReviewModule | None = None,
        defer: bool = False,
        project: SessionProjection,
    ) -> ReviewDecisionChangeResult:
        with self._lock:
            session = self._require_session_locked(scan)
            project(session)
            try:
                item = get_review_item(session, item_id)
                if (
                    expected_category is not None
                    and item.category != expected_category
                ):
                    raise ValueError("review item is unavailable for this surface")
                module = queue_module or self._module_for_category(item.category)
                queue = self._queue_snapshot_locked(module)
                if item_validator is not None and not item_validator(
                    session, item.id, queue
                ):
                    raise ValueError("review item is not primary on this surface")
                result = change_review_decisions(session, (item_id,), decision)
            except ValueError as error:
                raise ReviewItemNotFound(str(error)) from error
            self._session = result.session
            self._mark_handled_locked(module, item.id, defer=defer)
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
            for item_id in pending.preview.target_ids:
                item = get_review_item(change.session, item_id)
                self._mark_handled_locked(
                    self._module_for_category(item.category),
                    item.id,
                    defer=False,
                )
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

    def save_module(
        self,
        scan: ScanJobSnapshot,
        module: ReviewModule,
        *,
        project: SessionProjection,
    ) -> ModuleReviewSaveResult:
        with self._lock:
            session = self._require_session_locked(scan)
            project(session)
            result = save_review_module(session, module)
            self._session = result.session
            self._pending_page_decisions.clear()
            return result

    def revisit_skipped(
        self,
        scan: ScanJobSnapshot,
        module: ReviewModule,
    ) -> ModuleQueueSnapshot:
        with self._lock:
            self._require_session_locked(scan)
            deferred = self._module_deferred[module]
            self._module_handled[module].difference_update(deferred)
            deferred.clear()
            return self._queue_snapshot_locked(module)

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
                session = create_fresh_web_review_session_from_scan_result(
                    scan.result
                )
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
            module_queues=self._queue_snapshots_locked(),
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
        for values in self._module_handled.values():
            values.clear()
        for values in self._module_deferred.values():
            values.clear()

    def _drop_previews_for_session_locked(self, browser_session_id: str) -> None:
        self._pending_page_decisions = {
            token: pending
            for token, pending in self._pending_page_decisions.items()
            if pending.browser_session_id != browser_session_id
        }

    def _module_for_category(self, category: str) -> ReviewModule:
        for module in ReviewModule:
            if review_module_category(module) == category:
                return module
        raise ValueError("review item category has no consumer module")

    def _mark_handled_locked(
        self,
        module: ReviewModule,
        item_id: str,
        *,
        defer: bool,
    ) -> None:
        self._module_handled[module].add(item_id)
        if defer:
            self._module_deferred[module].add(item_id)
        else:
            self._module_deferred[module].discard(item_id)

    def _queue_snapshot_locked(
        self,
        module: ReviewModule,
    ) -> ModuleQueueSnapshot:
        return ModuleQueueSnapshot(
            module=module,
            handled_ids=tuple(sorted(self._module_handled[module])),
            deferred_ids=tuple(sorted(self._module_deferred[module])),
        )

    def _queue_snapshots_locked(self) -> tuple[ModuleQueueSnapshot, ...]:
        return tuple(self._queue_snapshot_locked(module) for module in ReviewModule)
