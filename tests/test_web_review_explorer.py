from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from organizer.application.scan_service import scan_root
from organizer.web.review_explorer import ReviewExplorerStore
from organizer.web.scan_jobs import ScanJobSnapshot


class ReviewExplorerStoreTests(unittest.TestCase):
    def test_store_clears_rows_for_running_and_failed_generations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = scan_root(root)
            store = ReviewExplorerStore(root)

            completed = store.snapshot(
                ScanJobSnapshot(status="completed", job_id="one", result=result)
            )
            self.assertIsNotNone(completed.session)

            running = store.snapshot(
                ScanJobSnapshot(status="scanning", job_id="two")
            )
            self.assertEqual(running.status, "scanning")
            self.assertIsNone(running.session)

            failed = store.snapshot(
                ScanJobSnapshot(
                    status="failed",
                    job_id="two",
                    error_message="safe failure",
                )
            )
            self.assertEqual(failed.status, "failed")
            self.assertIsNone(failed.session)

    def test_completed_generation_replaces_previous_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = scan_root(root)
            (root / "new.txt").write_text("new", encoding="utf-8")
            second = scan_root(root)
            store = ReviewExplorerStore(root)

            first_snapshot = store.snapshot(
                ScanJobSnapshot(status="completed", job_id="one", result=first)
            )
            second_snapshot = store.snapshot(
                ScanJobSnapshot(status="completed", job_id="two", result=second)
            )
            self.assertNotEqual(first_snapshot.generation_id, second_snapshot.generation_id)
            self.assertIsNot(first_snapshot.session, second_snapshot.session)


if __name__ == "__main__":
    unittest.main()
