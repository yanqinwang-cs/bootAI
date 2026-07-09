from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from organizer.models import MovePlanItem, ReviewedPlanItem
from organizer.review_state import (
    ReviewDecisionRecord,
    ReviewState,
    apply_review_state_to_items,
    load_review_state,
    review_state_from_json_data,
    review_state_path,
    save_review_state,
    update_review_state_from_items,
)


class ReviewStateLoadSaveTests(unittest.TestCase):
    def test_missing_state_loads_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = load_review_state(Path(directory))

            self.assertEqual(state.decisions, [])

    def test_valid_state_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = review_state_path(root)
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(valid_state_data()), encoding="utf-8")

            state = load_review_state(root)

            self.assertEqual(len(state.decisions), 1)
            self.assertEqual(state.decisions[0].decision, "rejected")
            self.assertEqual(state.decisions[0].source, Path("a.txt"))

    def test_malformed_json_and_unsupported_schema_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = review_state_path(root)
            path.parent.mkdir(parents=True)
            path.write_text("{", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_review_state(root)

        data = valid_state_data()
        data["schema_version"] = 2
        with self.assertRaises(ValueError):
            review_state_from_json_data(data)

    def test_invalid_decision_category_and_review_category_are_rejected(self) -> None:
        cases = [
            ("decision", "maybe"),
            ("category", "unknown"),
            ("review_category", "temporary"),
        ]
        for field, value in cases:
            data = valid_state_data()
            data["decisions"][0][field] = value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    review_state_from_json_data(data)

        data = valid_state_data(category="review_candidate", review_category="other")
        with self.assertRaises(ValueError):
            review_state_from_json_data(data)

    def test_absolute_and_traversal_paths_are_rejected(self) -> None:
        cases = [
            ("source", "/tmp/a.txt"),
            ("destination", "/tmp/out.txt"),
            ("source", "../a.txt"),
            ("destination", "../out.txt"),
        ]
        for field, value in cases:
            data = valid_state_data()
            data["decisions"][0][field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    review_state_from_json_data(data)

    def test_save_writes_under_review_state_and_does_not_create_operation_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            item = make_item(root, "D1", "duplicate", "a.txt", "AI_Review/duplicates/a.txt", "rejected")
            state = update_review_state_from_items(ReviewState([]), [item], root)

            path = save_review_state(state, root)
            data = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(path, root.resolve() / "AI_Review" / "review_state" / "review_decisions.json")
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(len(data["decisions"]), 1)
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())
            self.assertTrue((root / "a.txt").exists())


class ReviewStateMatchingTests(unittest.TestCase):
    def test_matching_remembered_rejected_duplicate_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            item = make_item(root, "D1", "duplicate", "a.txt", "AI_Review/duplicates/a.txt", "approved")
            state = update_review_state_from_items(
                ReviewState([]),
                [replace(item, decision="rejected")],
                root,
            )

            remembered = apply_review_state_to_items([item], state, root)

            self.assertEqual(remembered[0].decision, "rejected")
            self.assertEqual(remembered[0].memory_status, "rejected_remembered")
            self.assertEqual(remembered[0].remembered_decision, "rejected")

    def test_matching_remembered_approved_organization_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evosim.txt").write_text("notes", encoding="utf-8")
            item = make_item(
                root,
                "O1",
                "organization",
                "evosim.txt",
                "Organized/Evosim/notes/evosim.txt",
                "approved",
            )
            state = update_review_state_from_items(ReviewState([]), [item], root)

            remembered = apply_review_state_to_items([replace(item, decision="rejected")], state, root)

            self.assertEqual(remembered[0].decision, "approved")
            self.assertEqual(remembered[0].memory_status, "approved_remembered")

    def test_approved_duplicate_is_not_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            item = make_item(root, "D1", "duplicate", "a.txt", "AI_Review/duplicates/a.txt", "approved")

            state = update_review_state_from_items(ReviewState([]), [item], root)

            self.assertEqual(state.decisions, [])

    def test_review_candidate_matching_requires_review_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file.tmp").write_text("tmp", encoding="utf-8")
            item = make_item(
                root,
                "R1",
                "review_candidate",
                "file.tmp",
                "AI_Review/temporary/file.tmp",
                "rejected",
                review_category="temporary",
            )
            state = update_review_state_from_items(ReviewState([]), [item], root)
            other_category = replace(item, decision="approved", review_category="empty")

            remembered = apply_review_state_to_items([other_category], state, root)

            self.assertEqual(remembered[0].decision, "approved")
            self.assertEqual(remembered[0].memory_status, "new_suggestion")

    def test_non_matching_destination_does_not_apply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            item = make_item(root, "D1", "duplicate", "a.txt", "AI_Review/duplicates/a.txt", "rejected")
            state = update_review_state_from_items(ReviewState([]), [item], root)
            changed_destination = make_item(root, "D1", "duplicate", "a.txt", "AI_Review/other/a.txt", "approved")

            remembered = apply_review_state_to_items([changed_destination], state, root)

            self.assertEqual(remembered[0].decision, "approved")
            self.assertEqual(remembered[0].memory_status, "new_suggestion")

    def test_changed_size_or_modified_time_marks_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "a.txt"
            source.write_text("same", encoding="utf-8")
            item = make_item(root, "D1", "duplicate", "a.txt", "AI_Review/duplicates/a.txt", "rejected")
            state = update_review_state_from_items(ReviewState([]), [item], root)
            source.write_text("changed", encoding="utf-8")

            remembered = apply_review_state_to_items([replace(item, decision="approved")], state, root)

            self.assertEqual(remembered[0].decision, "approved")
            self.assertEqual(remembered[0].memory_status, "stale_prior_decision")
            self.assertEqual(remembered[0].remembered_decision, "rejected")

    def test_missing_source_decision_is_ignored_and_preserved(self) -> None:
        state = ReviewState(
            decisions=[
                ReviewDecisionRecord(
                    decision_id="20260709T120000000000Z-001",
                    created_at="20260709T120000000000Z",
                    updated_at="20260709T120000000000Z",
                    decision="rejected",
                    category="duplicate",
                    review_category=None,
                    source=Path("missing.txt"),
                    destination=Path("AI_Review/duplicates/missing.txt"),
                    reason="remembered rejected review decision for D1",
                    fingerprint={"size_bytes": 4, "modified_ns": 1},
                )
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            item = make_item(root, "D1", "duplicate", "a.txt", "AI_Review/duplicates/a.txt", "approved")

            remembered = apply_review_state_to_items([item], state, root)
            updated = update_review_state_from_items(state, [replace(item, decision="rejected")], root)

            self.assertEqual(remembered[0].memory_status, "new_suggestion")
            self.assertEqual(len(updated.decisions), 2)


def valid_state_data(
    category: str = "duplicate",
    review_category: str | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "decisions": [
            {
                "decision_id": "20260709T120000000000Z-001",
                "created_at": "20260709T120000000000Z",
                "updated_at": "20260709T120000000000Z",
                "decision": "rejected",
                "category": category,
                "review_category": review_category,
                "source": "a.txt",
                "destination": "AI_Review/duplicates/a.txt",
                "reason": "remembered rejected review decision for D1",
                "fingerprint": {
                    "size_bytes": 4,
                    "modified_ns": 1,
                },
                "extra": "ignored",
            }
        ],
    }


def make_item(
    root: Path,
    item_id: str,
    category: str,
    source: str,
    destination: str,
    decision: str,
    review_category: str | None = None,
) -> ReviewedPlanItem:
    return ReviewedPlanItem(
        id=item_id,
        category=category,
        decision=decision,
        review_category=review_category,
        plan_item=MovePlanItem(
            source=root / source,
            destination=root / destination,
            reason="test reviewed plan item",
            confidence=100,
            operation="dry-run move",
            overwrite_risk=False,
        ),
    )


if __name__ == "__main__":
    unittest.main()
