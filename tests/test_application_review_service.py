import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from organizer.application.review_service import (
    apply_current_page_decision,
    change_review_decisions,
    create_review_session,
    find_review_conflicts,
    get_review_item,
    get_review_view,
    preview_current_page_decision,
    resume_review_session,
    save_review_session,
    summarize_review_session,
    update_review_filter,
    update_review_page_size,
    update_review_sort,
)
from organizer.models import MovePlanItem, ReviewedPlanItem
from organizer.review_session import (
    DECISION_APPROVED,
    DECISION_REJECTED,
    ReviewViewState,
    load_reviewed_plan_items,
    save_reviewed_plan,
)
from organizer.review_state import ReviewState
from organizer.application.view_models import ReviewApplicationSession


class ReviewServiceTests(unittest.TestCase):
    def test_create_session_reuses_rows_and_review_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")

            session = create_review_session(root)

            self.assertEqual(session.root, root.resolve())
            self.assertEqual(tuple(item.id for item in session.items), ("D1",))
            self.assertIsInstance(session.review_state, ReviewState)
            self.assertFalse(session.review_state_ignored)
            self.assertTrue(session.persist_review_state)
            self.assertFalse(session.dirty)

            ignored = create_review_session(root, ignore_review_state=True)
            self.assertTrue(ignored.review_state_ignored)
            self.assertIsNone(ignored.review_state)

    def test_decision_changes_are_immutable_and_track_dirty_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            original = create_review_session(root)

            change = change_review_decisions(original, ["d1", "D1"], DECISION_REJECTED)

            self.assertIsNot(change.session, original)
            self.assertEqual(get_review_item(original, "D1").decision, DECISION_APPROVED)
            self.assertEqual(get_review_item(change.session, "D1").decision, DECISION_REJECTED)
            self.assertEqual(change.changed_ids, ("D1",))
            self.assertEqual(change.idempotent_ids, ())
            self.assertFalse(original.dirty)
            self.assertTrue(change.session.dirty)

            idempotent = change_review_decisions(
                change.session,
                ["D1"],
                DECISION_REJECTED,
            )
            self.assertEqual(idempotent.changed_ids, ())
            self.assertEqual(idempotent.idempotent_ids, ("D1",))

    def test_view_filter_sort_page_and_page_decision_delegate_to_engine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            (root / "notes copy.txt").write_text("copy", encoding="utf-8")
            session = create_review_session(root)
            session = update_review_page_size(session, "1")
            session = update_review_sort(session, "id", "desc")
            session = update_review_filter(session, "decision", "approved")

            view = get_review_view(session)
            self.assertEqual(view.page_size, 1)
            self.assertEqual(len(view.rows), 1)

            preview = preview_current_page_decision(session, DECISION_REJECTED)
            updated = apply_current_page_decision(session, preview)
            self.assertEqual(updated.changed_ids, preview.change_ids)
            self.assertTrue(updated.session.dirty)
            self.assertEqual(session.items[0].decision, DECISION_APPROVED)

    def test_summary_and_conflicts_reuse_existing_review_logic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source.txt"
            source.write_text("x", encoding="utf-8")
            items = (
                _review_item("D1", source, root / "AI_Review" / "duplicates" / "source.txt"),
                _review_item("O1", source, root / "Organized" / "source.txt"),
            )
            session = _manual_session(root, items)

            summary = summarize_review_session(session)
            conflicts = find_review_conflicts(session)

            self.assertEqual(summary["approved_move_conflict_count"], 1)
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].conflict_type, "source")

    def test_save_returns_new_clean_session_and_preserves_all_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            (root / "notes copy.txt").write_text("copy", encoding="utf-8")
            session = create_review_session(root)
            changed = change_review_decisions(
                session,
                [session.items[0].id],
                DECISION_REJECTED,
            ).session
            hidden = update_review_filter(changed, "decision", "approved")

            result = save_review_session(hidden)
            loaded = load_reviewed_plan_items(result.reviewed_plan_path, root)

            self.assertTrue(hidden.dirty)
            self.assertFalse(result.session.dirty)
            self.assertEqual(len(loaded), len(hidden.items))
            self.assertIsNotNone(result.review_state_path)
            self.assertTrue(result.reviewed_plan_path.exists())
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())

    def test_resume_preserves_decisions_and_saves_collision_safe_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            source_session = create_review_session(root)
            source_path = save_reviewed_plan(list(source_session.items), root)

            resumed = resume_review_session(root, source_path)
            result = save_review_session(resumed)

            self.assertEqual(resumed.items, source_session.items)
            self.assertFalse(resumed.persist_review_state)
            self.assertIsNone(result.review_state_path)
            self.assertNotEqual(result.reviewed_plan_path, source_path)
            self.assertTrue(source_path.exists())

    def test_failed_save_leaves_original_session_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            dirty = change_review_decisions(
                create_review_session(root),
                ["D1"],
                DECISION_REJECTED,
            ).session

            with mock.patch(
                "organizer.application.review_service.save_reviewed_plan",
                side_effect=ValueError("simulated save failure"),
            ):
                with self.assertRaisesRegex(ValueError, "simulated save failure"):
                    save_review_session(dirty)

            self.assertTrue(dirty.dirty)
            self.assertIsNone(dirty.saved_plan_path)

    def test_service_does_not_prompt_print_or_depend_on_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__import__("organizer.application.review_service", fromlist=["x"]).__file__)
            with mock.patch(
                "builtins.input",
                side_effect=AssertionError("review service must not prompt"),
            ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                create_review_session(root)

            self.assertEqual(stdout.getvalue(), "")
            self.assertNotIn("organizer.executor", source.read_text(encoding="utf-8"))


def _review_item(item_id: str, source: Path, destination: Path) -> ReviewedPlanItem:
    return ReviewedPlanItem(
        id=item_id,
        category="duplicate" if item_id.startswith("D") else "organization",
        decision=DECISION_APPROVED,
        plan_item=MovePlanItem(
            source=source,
            destination=destination,
            reason="test",
            confidence=100,
            operation="dry-run move",
            overwrite_risk=False,
        ),
    )


def _manual_session(
    root: Path,
    items: tuple[ReviewedPlanItem, ...],
) -> ReviewApplicationSession:
    return ReviewApplicationSession(
        root=root,
        items=items,
        view_state=ReviewViewState(),
        source_path=None,
        saved_plan_path=None,
        review_state=ReviewState(decisions=[]),
        persist_review_state=True,
        review_state_ignored=False,
        saved_decisions=tuple(sorted((item.id, item.decision) for item in items)),
    )


if __name__ == "__main__":
    unittest.main()
