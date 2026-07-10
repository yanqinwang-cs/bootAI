from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from organizer.application.review_service import (
    get_review_view,
    update_review_filter,
    update_review_page_size,
)
from organizer.application.scan_service import scan_root
from organizer.web.review_explorer import (
    ReviewConfirmationRejected,
    ReviewExplorerStore,
    ReviewPreviewUnavailable,
)
from organizer.web.scan_jobs import ScanJobSnapshot


class ApplicationReviewWebSessionTests(unittest.TestCase):
    def test_single_row_updates_replace_immutable_session_and_track_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            result = scan_root(root)
            scan = ScanJobSnapshot(
                status="completed",
                job_id="one",
                result=result,
            )
            store = ReviewExplorerStore(root)
            original = store.snapshot(scan).session
            assert original is not None

            changed = store.change_decision(
                scan,
                "D1",
                "rejected",
                project=lambda session: session,
            )
            current = store.snapshot(scan).session
            assert current is not None

            self.assertIsNot(changed.session, original)
            self.assertEqual(original.items[0].decision, "approved")
            self.assertEqual(current.items[0].decision, "rejected")
            self.assertTrue(current.dirty)

            idempotent = store.change_decision(
                scan,
                "D1",
                "rejected",
                project=lambda session: session,
            )
            self.assertEqual(idempotent.changed_ids, ())
            self.assertTrue(idempotent.session.dirty)

    def test_server_held_preview_freezes_only_filtered_current_page_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(1, 6):
                (root / f"backup copy {index}.txt").write_text(
                    str(index),
                    encoding="utf-8",
                )
            result = scan_root(root)
            scan = ScanJobSnapshot(
                status="completed",
                job_id="one",
                result=result,
            )
            store = ReviewExplorerStore(root)

            def project(session):
                session = update_review_filter(
                    session,
                    "category",
                    "review_candidate",
                )
                return update_review_page_size(session, "2")

            pending = store.preview_page_decision(
                scan,
                "browser-one",
                "rejected",
                project=project,
                view_query=(("category", "review_candidate"),),
            )
            assert pending.preview_token is not None
            before = store.snapshot(scan).session
            assert before is not None
            off_page = {
                item.id for item in before.items
            } - set(pending.preview.target_ids)

            confirmed = store.confirm_page_decision(
                scan,
                "browser-one",
                pending.preview_token,
                "REJECT CURRENT PAGE",
            )
            after = confirmed.change.session

            self.assertEqual(len(pending.preview.target_ids), 2)
            self.assertEqual(
                {
                    item.id
                    for item in after.items
                    if item.decision == "rejected"
                },
                set(pending.preview.target_ids),
            )
            self.assertTrue(
                all(
                    item.decision == "approved"
                    for item in after.items
                    if item.id in off_page
                )
            )
            self.assertNotIn(str(root), pending.preview_token)
            with self.assertRaises(ReviewPreviewUnavailable):
                store.confirm_page_decision(
                    scan,
                    "browser-one",
                    pending.preview_token,
                    "REJECT CURRENT PAGE",
                )

    def test_wrong_confirmation_consumes_preview_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backup copy.txt").write_text("x", encoding="utf-8")
            result = scan_root(root)
            scan = ScanJobSnapshot(
                status="completed",
                job_id="one",
                result=result,
            )
            store = ReviewExplorerStore(root)
            pending = store.preview_page_decision(
                scan,
                "browser-one",
                "rejected",
                project=lambda session: session,
                view_query=(),
            )
            assert pending.preview_token is not None

            with self.assertRaises(ReviewConfirmationRejected):
                store.confirm_page_decision(
                    scan,
                    "browser-one",
                    pending.preview_token,
                    "WRONG",
                )

            session = store.snapshot(scan).session
            assert session is not None
            self.assertFalse(session.dirty)
            self.assertTrue(all(item.decision == "approved" for item in session.items))
            with self.assertRaises(ReviewPreviewUnavailable):
                store.confirm_page_decision(
                    scan,
                    "browser-one",
                    pending.preview_token,
                    "REJECT CURRENT PAGE",
                )


if __name__ == "__main__":
    unittest.main()
