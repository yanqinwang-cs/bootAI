from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from copy import deepcopy
import logging
from pathlib import Path
import secrets
from threading import Lock, Thread
from typing import Callable

from organizer.application.scan_service import (
    ScanApplicationResult,
    scan_root,
    write_scan_report,
)

logger = logging.getLogger(__name__)


class ScanAlreadyRunning(RuntimeError):
    pass


@dataclass(frozen=True)
class ScanJobSnapshot:
    status: str
    job_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: ScanApplicationResult | None = None
    report_path: Path | None = None
    error_message: str | None = None


ScanCallable = Callable[[Path], ScanApplicationResult]
ReportWriter = Callable[[ScanApplicationResult], Path]


class ScanJobController:
    """Own one root-bound, in-process scan job without web-framework concerns."""

    def __init__(
        self,
        root: Path,
        *,
        scan: ScanCallable = scan_root,
        write_report: ReportWriter = write_scan_report,
    ) -> None:
        self._root = root.resolve()
        self._scan = scan
        self._write_report = write_report
        self._lock = Lock()
        self._snapshot = ScanJobSnapshot(status="not_started")

    def snapshot(self) -> ScanJobSnapshot:
        with self._lock:
            return deepcopy(self._snapshot)

    def start(self) -> ScanJobSnapshot:
        with self._lock:
            if self._snapshot.status == "scanning":
                raise ScanAlreadyRunning("a scan is already running")
            job_id = secrets.token_urlsafe(18)
            self._snapshot = ScanJobSnapshot(
                status="scanning",
                job_id=job_id,
                started_at=_now(),
            )
        Thread(
            target=self._run,
            args=(job_id,),
            name="bootai-scan-job",
            daemon=True,
        ).start()
        return self.snapshot()

    def _run(self, job_id: str) -> None:
        try:
            result = self._scan(self._root)
            report_path = self._write_report(result)
        except Exception as error:
            logger.error(
                "scan job failed for generation %s (%s)",
                job_id,
                type(error).__name__,
            )
            self._fail(job_id, error)
            return
        self._complete(job_id, result, report_path)

    def _complete(
        self,
        job_id: str,
        result: ScanApplicationResult,
        report_path: Path,
    ) -> None:
        with self._lock:
            if self._snapshot.job_id != job_id:
                return
            self._snapshot = ScanJobSnapshot(
                status="completed",
                job_id=job_id,
                started_at=self._snapshot.started_at,
                completed_at=_now(),
                result=result,
                report_path=report_path,
            )

    def _fail(self, job_id: str, error: Exception) -> None:
        del error
        with self._lock:
            if self._snapshot.job_id != job_id:
                return
            self._snapshot = ScanJobSnapshot(
                status="failed",
                job_id=job_id,
                started_at=self._snapshot.started_at,
                completed_at=_now(),
                error_message=(
                    "The scan could not be completed. "
                    "No files were moved. Please try again."
                ),
            )


def _now() -> datetime:
    return datetime.now(timezone.utc)
