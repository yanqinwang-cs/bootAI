from __future__ import annotations

from pathlib import Path
import tempfile
from threading import Event
import time
import unittest

from organizer.application.view_models import ScanApplicationResult, ScanSummary
from organizer.web.scan_jobs import ScanAlreadyRunning, ScanJobController


def _result(root: Path) -> ScanApplicationResult:
    return ScanApplicationResult(
        root=root,
        report={"summary": {}, "warnings": []},
        summary=ScanSummary(1, 10, 0, 0, 0, 0),
        warnings=(),
    )


class ScanJobControllerTests(unittest.TestCase):
    def test_successful_job_writes_before_completed_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            written = root / "AI_Review" / "reports" / "report.json"
            gate = Event()

            def scan(path: Path) -> ScanApplicationResult:
                gate.wait(timeout=2)
                return _result(path)

            controller = ScanJobController(
                root,
                scan=scan,
                write_report=lambda result: written,
            )

            started = controller.start()
            self.assertEqual(started.status, "scanning")
            self.assertIsNotNone(started.job_id)
            gate.set()
            self._wait_for_status(controller, "completed")
            self.assertEqual(controller.snapshot().status, "completed")
            self.assertEqual(controller.snapshot().report_path, written)

    def test_duplicate_start_is_rejected_while_running(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gate = Event()
            root = Path(directory)

            def scan(path: Path) -> ScanApplicationResult:
                gate.wait(timeout=2)
                return _result(path)

            controller = ScanJobController(root, scan=scan, write_report=lambda _: root / "report.json")
            controller.start()
            with self.assertRaises(ScanAlreadyRunning):
                controller.start()
            gate.set()
            self._wait_for_status(controller, "completed")

    def test_scan_and_report_failures_are_user_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = ScanJobController(
                root,
                scan=lambda _: (_ for _ in ()).throw(RuntimeError("secret detail")),
                write_report=lambda _: root / "report.json",
            )
            controller.start()
            self._wait_for_status(controller, "failed")
            snapshot = controller.snapshot()
            self.assertNotIn("secret detail", snapshot.error_message or "")
            self.assertNotIn("Traceback", snapshot.error_message or "")

            controller = ScanJobController(
                root,
                scan=lambda path: _result(path),
                write_report=lambda _: (_ for _ in ()).throw(OSError("secret detail")),
            )
            controller.start()
            self._wait_for_status(controller, "failed")
            self.assertIsNone(controller.snapshot().result)

    def test_stale_generation_cannot_overwrite_newer_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = ScanJobController(
                root,
                scan=lambda path: _result(path),
                write_report=lambda _: root / "report.json",
            )
            first = controller.start()
            self._wait_for_status(controller, "completed")
            second = controller.start()
            controller._fail(first.job_id or "", RuntimeError("stale"))
            self.assertEqual(controller.snapshot().job_id, second.job_id)
            self._wait_for_status(controller, "completed")

    @staticmethod
    def _wait_for_status(controller: ScanJobController, status: str) -> None:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if controller.snapshot().status == status:
                return
            time.sleep(0.01)
        raise AssertionError(f"job did not reach {status}")


if __name__ == "__main__":
    unittest.main()
