from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from organizer.models import MovePlanItem, ReviewedPlanItem
from organizer.review_session import (
    DECISION_APPROVED,
    DECISION_REJECTED,
    DECISION_UNDECIDED,
    ReviewViewState,
    apply_page_decision_change,
    build_review_view,
    preview_page_decision_change,
    set_review_filter,
    set_review_page,
    set_review_page_size,
    set_review_sort,
)


class PageDecisionHelperTests(unittest.TestCase):
    def test_preview_targets_only_filtered_sorted_current_page(self) -> None:
        root = Path("/tmp/review-root")
        items = make_items(root)
        state = set_review_filter(
            ReviewViewState(),
            "category",
            "organization",
        )
        state = set_review_sort(state, "source", "desc")
        state = set_review_page_size(state, "2")
        state = set_review_page(state, "2", items, root)

        preview = preview_page_decision_change(
            items,
            state,
            root,
            DECISION_APPROVED,
        )

        self.assertEqual(preview.target_ids, ("O003",))
        self.assertEqual(preview.change_ids, ("O003",))
        self.assertEqual((preview.page, preview.total_pages), (2, 2))
        self.assertEqual(preview.matching_count, 3)
        self.assertEqual(preview.total_count, 7)

    def test_apply_changes_only_preview_ids_and_preserves_metadata(self) -> None:
        root = Path("/tmp/review-root")
        items = make_items(root)
        state = set_review_page_size(ReviewViewState(), "2")
        preview = preview_page_decision_change(
            items,
            state,
            root,
            DECISION_REJECTED,
        )
        before = {item.id: item for item in items}

        updated = apply_page_decision_change(items, preview)
        after = {item.id: item for item in updated}

        self.assertEqual(preview.target_ids, ("D001", "D002"))
        self.assertEqual(after["D001"].decision, DECISION_REJECTED)
        self.assertEqual(after["D002"].decision, DECISION_REJECTED)
        self.assertEqual(after["O001"].decision, before["O001"].decision)
        self.assertEqual(after["D001"].id, before["D001"].id)
        self.assertEqual(after["D001"].plan_item, before["D001"].plan_item)

    def test_idempotent_rows_are_excluded_from_changes(self) -> None:
        root = Path("/tmp/review-root")
        items = make_items(root)
        state = set_review_filter(
            ReviewViewState(),
            "decision",
            "approved",
        )
        preview = preview_page_decision_change(
            items,
            state,
            root,
            DECISION_APPROVED,
        )

        self.assertTrue(preview.target_ids)
        self.assertEqual(preview.change_ids, ())
        self.assertEqual(preview.already_count, len(preview.target_ids))
        self.assertIs(apply_page_decision_change(items, preview), items)

    def test_all_three_decisions_use_expected_confirmations(self) -> None:
        root = Path("/tmp/review-root")
        items = make_items(root)
        expected = {
            DECISION_APPROVED: "APPROVE CURRENT PAGE",
            DECISION_REJECTED: "REJECT CURRENT PAGE",
            DECISION_UNDECIDED: "UNDECIDE CURRENT PAGE",
        }
        for decision, confirmation in expected.items():
            with self.subTest(decision=decision):
                preview = preview_page_decision_change(
                    items,
                    ReviewViewState(page_size=1),
                    root,
                    decision,
                )
                self.assertEqual(preview.confirmation, confirmation)


class PageDecisionCliTests(unittest.TestCase):
    def test_exact_confirmations_update_current_page_only(self) -> None:
        commands = [
            ("approve-page", "APPROVE CURRENT PAGE", "approved"),
            ("reject-page", "REJECT CURRENT PAGE", "rejected"),
            ("undecide-page", "UNDECIDE CURRENT PAGE", "undecided"),
        ]
        for command, confirmation, decision in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = write_reviewed_plan(root)
                result = run_cli(
                    root,
                    "--resume-reviewed-plan",
                    str(plan),
                    input_text=(
                        f"page-size 3\n{command}\n{confirmation}\nsave\nquit\n"
                    ),
                )
                saved = read_json(plan.with_name("reviewed_plan_1.json"))
                decisions = {item["id"]: item["decision"] for item in saved["items"]}

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(decisions["D001"], decision)
                self.assertEqual(decisions["D002"], decision)
                self.assertEqual(decisions["O001"], decision)
                self.assertEqual(decisions["O002"], "undecided")
                self.assertIn("This changes review decisions only", result.stdout)
                self.assertIn("No files were moved", result.stdout)
                self.assertFalse((root / "AI_Review" / "operation_logs").exists())

    def test_wrong_blank_and_eof_confirmation_cancel_without_changes(self) -> None:
        confirmation_inputs = ["WRONG\nquit\n", "\nquit\n", ""]
        for confirmation_input in confirmation_inputs:
            with self.subTest(input=confirmation_input), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = write_reviewed_plan(root)
                original = plan.read_text(encoding="utf-8")
                result = run_cli(
                    root,
                    "--resume-reviewed-plan",
                    str(plan),
                    input_text=f"page-size 1\nreject-page\n{confirmation_input}",
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Page decision change cancelled", result.stdout)
                self.assertEqual(plan.read_text(encoding="utf-8"), original)
                self.assertFalse(plan.with_name("reviewed_plan_1.json").exists())

    def test_preview_precedes_confirmation_and_reports_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text="page-size 3\napprove-page\nWRONG\nquit\n",
            )

            preview_index = result.stdout.index("Current-page decision preview")
            prompt_index = result.stdout.index("Type APPROVE CURRENT PAGE")
            self.assertLess(preview_index, prompt_index)
            self.assertIn("target rows: 3", result.stdout)
            self.assertIn("stable IDs: D001, D002, O001", result.stdout)
            self.assertIn("current decisions:", result.stdout)
            self.assertIn("categories:", result.stdout)

    def test_empty_and_fully_idempotent_pages_do_not_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            empty = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text=(
                    "filter review_category orphan_code\napprove-page\nquit\n"
                ),
            )
            idempotent = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text="filter decision approved\napprove-page\nquit\n",
            )

            self.assertIn("No rows are displayed", empty.stdout)
            self.assertNotIn("Type APPROVE CURRENT PAGE", empty.stdout)
            self.assertIn("No changes are required", idempotent.stdout)
            self.assertNotIn("Type APPROVE CURRENT PAGE", idempotent.stdout)

    def test_decision_filter_recalculates_and_clamps_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text=(
                    "filter decision undecided\n"
                    "page-size 2\n"
                    "page 2\n"
                    "approve-page\n"
                    "APPROVE CURRENT PAGE\n"
                    "view\n"
                    "quit\n"
                ),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("filters: decision=undecided", result.stdout)
            self.assertIn("matching rows: 2", result.stdout)
            self.assertIn("page: 1 of 1", result.stdout)

    def test_bulk_decisions_do_not_autosave_or_call_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            original = plan.read_text(encoding="utf-8")
            argv = [
                "organizer.cli",
                str(root),
                "--resume-reviewed-plan",
                str(plan),
            ]
            with mock.patch("sys.argv", argv), mock.patch(
                "builtins.input",
                side_effect=[
                    "page-size 1",
                    "reject-page",
                    "REJECT CURRENT PAGE",
                    "quit",
                ],
            ), mock.patch(
                "organizer.cli.apply_move_plan",
                side_effect=AssertionError("executor must not be called"),
            ), mock.patch("sys.stdout", new_callable=io.StringIO):
                from organizer.cli import main

                exit_code = main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(plan.read_text(encoding="utf-8"), original)
            self.assertFalse(plan.with_name("reviewed_plan_1.json").exists())
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())

    def test_new_review_session_supports_bulk_page_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            result = run_cli(
                root,
                "--review-plans",
                input_text=(
                    "reject-page\nREJECT CURRENT PAGE\nsummary\nquit\n"
                ),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Updated 1 review rows to rejected", result.stdout)
            self.assertIn("total rejected moves: 1", result.stdout)


def make_items(root: Path) -> list[ReviewedPlanItem]:
    specs = [
        ("D001", "duplicate", "g.txt", "approved"),
        ("D002", "duplicate", "f.txt", "approved"),
        ("O001", "organization", "e.txt", "undecided"),
        ("O002", "organization", "d.txt", "undecided"),
        ("O003", "organization", "c.txt", "rejected"),
        ("R001", "review_candidate", "b.tmp", "undecided"),
        ("R002", "review_candidate", "a.tmp", "rejected"),
    ]
    return [
        ReviewedPlanItem(
            id=item_id,
            category=category,
            decision=decision,
            review_category=("temporary" if category == "review_candidate" else None),
            plan_item=MovePlanItem(
                source=root / source,
                destination=root / "AI_Review" / category / source,
                reason=f"review row {item_id}",
                confidence=100,
                operation="dry-run move",
                overwrite_risk=False,
            ),
        )
        for item_id, category, source, decision in specs
    ]


def write_reviewed_plan(root: Path) -> Path:
    path = root / "AI_Review" / "review_sessions" / "reviewed_plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "created_at": "2026-07-10T12:00:00+00:00",
        "scan_root": ".",
        "plan_type": "batch_review",
        "summary": {},
        "items": [
            {
                "id": item.id,
                "category": item.category,
                "decision": item.decision,
                "source": item.plan_item.source.relative_to(root).as_posix(),
                "destination": item.plan_item.destination.relative_to(root).as_posix(),
                "reason": item.plan_item.reason,
                "confidence": item.plan_item.confidence,
                "operation": item.plan_item.operation,
                "overwrite_risk": item.plan_item.overwrite_risk,
                **(
                    {"review_category": item.review_category}
                    if item.review_category is not None
                    else {}
                ),
            }
            for item in make_items(root)
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    assert isinstance(data, dict)
    return data


def run_cli(
    root: Path,
    *args: str,
    input_text: str = "",
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, "-m", "organizer.cli", str(root), *args],
        input=input_text,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()
