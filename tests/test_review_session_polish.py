from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from organizer import cli as cli_module


class ReviewSessionHelpAndErrorTests(unittest.TestCase):
    def test_help_is_grouped_complete_and_decision_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)

            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text="help\nquit\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            for heading in (
                "Inspection",
                "Single-row decisions",
                "Current-page decisions",
                "View controls",
                "Session actions",
            ):
                self.assertIn(heading, result.stdout)
            for command in (
                "show",
                "view",
                "summary",
                "details <ID>",
                "conflicts",
                "approve <IDs...>",
                "reject <IDs...>",
                "undecide <IDs...>",
                "approve-page",
                "reject-page",
                "undecide-page",
                "filter <field> <value>",
                "clear-filter",
                "sort <field> [asc|desc]",
                "clear-sort",
                "page next|prev|<number>",
                "page-size <number>",
                "save",
                "apply",
                "quit",
                "help",
            ):
                self.assertIn(command, result.stdout)
            self.assertIn("review decisions only; no files move", result.stdout)
            self.assertIn("exact-confirm approved file moves", result.stdout)

    def test_specific_errors_preserve_decisions_view_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            original = plan.read_text(encoding="utf-8")

            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text=(
                    "filter category organization\n"
                    "filt decision approved\n"
                    "filter path notes\n"
                    "filter decision pending\n"
                    "sort size\n"
                    "sort source sideways\n"
                    "page nowhere\n"
                    "page-size 0\n"
                    "reject O999\n"
                    "view\n"
                    "quit\n"
                ),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Unknown command: filt", result.stdout)
            self.assertIn("Unknown filter field: path", result.stdout)
            self.assertIn("Supported fields: category, decision, review_category", result.stdout)
            self.assertIn("Invalid filter value for decision: pending", result.stdout)
            self.assertIn("Supported values: approved, rejected, undecided", result.stdout)
            self.assertIn("Unknown sort field: size", result.stdout)
            self.assertIn("Invalid sort direction: sideways", result.stdout)
            self.assertIn("Supported directions: asc, desc", result.stdout)
            self.assertIn("Invalid page: nowhere", result.stdout)
            self.assertIn("Invalid page size: 0", result.stdout)
            self.assertIn("Row ID not found: O999", result.stdout)
            self.assertIn("filters: category=organization", result.stdout)
            self.assertIn("unsaved decision changes: no", result.stdout)
            self.assertEqual(plan.read_text(encoding="utf-8"), original)
            self.assertFalse(plan.with_name("reviewed_plan_1.json").exists())


class ReviewSessionDirtyStateTests(unittest.TestCase):
    def test_resumed_session_starts_clean_and_idempotent_change_stays_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)

            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text="approve D1\nview\nquit\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Updated 0 review rows to approved", result.stdout)
            self.assertIn("unsaved decision changes: no", result.stdout)
            self.assertNotIn("QUIT WITHOUT SAVING", result.stdout)

    def test_single_and_page_changes_mark_dirty_and_view_commands_do_not_clear_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)

            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text=(
                    "reject D1\n"
                    "filter category organization\n"
                    "sort source desc\n"
                    "view\n"
                    "clear-filter\n"
                    "page-size 1\n"
                    "approve-page\n"
                    "APPROVE CURRENT PAGE\n"
                    "view\n"
                    "quit\n"
                    "QUIT WITHOUT SAVING\n"
                ),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreaterEqual(
                result.stdout.count("unsaved decision changes: yes"),
                2,
            )
            self.assertIn("No files were moved", result.stdout)
            self.assertFalse(plan.with_name("reviewed_plan_1.json").exists())

    def test_restoring_saved_decision_returns_session_to_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)

            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text="reject D1\napprove D1\nview\nquit\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("unsaved decision changes: no", result.stdout)
            self.assertNotIn("QUIT WITHOUT SAVING", result.stdout)

    def test_successful_save_clears_dirty_and_does_not_serialize_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)

            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text="reject D1\nsave\nview\nquit\n",
            )
            saved = plan.with_name("reviewed_plan_1.json")
            data = json.loads(saved.read_text(encoding="utf-8"))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Reviewed plan saved: AI_Review/review_sessions/reviewed_plan_1.json", result.stdout)
            self.assertIn("Rows saved: 3", result.stdout)
            self.assertIn("Approved: 0", result.stdout)
            self.assertIn("Rejected: 2", result.stdout)
            self.assertIn("Undecided: 1", result.stdout)
            self.assertIn("Approved conflicts: 0", result.stdout)
            self.assertTrue(result.stdout.rstrip().endswith("Exiting review session without applying."))
            self.assertIn("unsaved decision changes: no", result.stdout)
            self.assertNotIn("has_unsaved_decision_changes", data)
            self.assertNotIn("dirty", data)
            self.assertEqual(plan.read_text(encoding="utf-8"), original_plan_text())

    def test_failed_save_preserves_dirty_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            argv = [
                "organizer.cli",
                str(root),
                "--resume-reviewed-plan",
                str(plan),
            ]
            with mock.patch("sys.argv", argv), mock.patch(
                "builtins.input",
                side_effect=[
                    "reject D1",
                    "save",
                    "view",
                    "quit",
                    "QUIT WITHOUT SAVING",
                ],
            ), mock.patch(
                "organizer.cli.save_resumed_reviewed_plan",
                side_effect=ValueError("simulated save failure"),
            ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                exit_code = cli_module.main()

            self.assertEqual(exit_code, 0)
            self.assertIn("Error: simulated save failure", stdout.getvalue())
            self.assertIn("unsaved decision changes: yes", stdout.getvalue())
            self.assertFalse(plan.with_name("reviewed_plan_1.json").exists())


class ReviewSessionQuitAndSummaryTests(unittest.TestCase):
    def test_dirty_quit_requires_exact_confirmation_and_cancel_preserves_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            original = plan.read_text(encoding="utf-8")

            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text=(
                    "reject D1\n"
                    "quit\n"
                    "WRONG\n"
                    "details D1\n"
                    "quit\n"
                    "\n"
                    "details D1\n"
                    "quit\n"
                    "QUIT WITHOUT SAVING\n"
                ),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("Quit cancelled"), 2)
            self.assertIn("Unsaved review-decision changes will be lost", result.stdout)
            self.assertIn("This affects review decisions only. No files will be moved", result.stdout)
            self.assertGreaterEqual(result.stdout.count("decision: rejected"), 2)
            self.assertEqual(plan.read_text(encoding="utf-8"), original)
            self.assertFalse(plan.with_name("reviewed_plan_1.json").exists())

    def test_eof_and_keyboard_interrupt_cancel_quit_confirmation(self) -> None:
        for error in (EOFError(), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__), mock.patch(
                "builtins.input",
                side_effect=error,
            ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                self.assertFalse(cli_module._confirm_quit_without_saving())
                self.assertIn("Quit cancelled", stdout.getvalue())

    def test_generated_and_resumed_headers_use_clear_sources_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            generated = run_cli(root, "--review-plans", input_text="quit\n")
            plan = write_reviewed_plan(root)
            resumed = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text="quit\n",
            )

            self.assertIn("Source: generated review plans", generated.stdout)
            self.assertIn("Rows: 1", generated.stdout)
            self.assertIn("Source: AI_Review/review_sessions/reviewed_plan.json", resumed.stdout)
            self.assertIn("Rows: 3", resumed.stdout)
            self.assertIn("Approved: 1", resumed.stdout)
            self.assertIn("Rejected: 1", resumed.stdout)
            self.assertIn("Undecided: 1", resumed.stdout)
            self.assertNotIn(str(root), resumed.stdout)


class ReviewSessionConflictPolishTests(unittest.TestCase):
    def test_conflicts_are_relative_ordered_and_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_conflicted_plan(root)
            original = plan.read_text(encoding="utf-8")

            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text="conflicts\nquit\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Approved conflicts: 2", result.stdout)
            source_heading = "Duplicate approved source: shared.txt"
            destination_heading = "Duplicate approved destination: Organized/shared.txt"
            self.assertLess(result.stdout.index(source_heading), result.stdout.index(destination_heading))
            self.assertIn("  D1: shared.txt", result.stdout)
            self.assertIn("  O1: shared.txt", result.stdout)
            self.assertIn("  O2: Organized/shared.txt", result.stdout)
            self.assertIn("  R1: Organized/shared.txt", result.stdout)
            self.assertNotIn(str(root), result.stdout)
            self.assertEqual(plan.read_text(encoding="utf-8"), original)
            self.assertFalse(plan.with_name("reviewed_plan_1.json").exists())
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())

    def test_zero_conflicts_is_concise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text="conflicts\nquit\n",
            )

            self.assertIn("Approved conflicts: 0", result.stdout)


def run_cli(
    root: Path,
    *args: str,
    input_text: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "organizer.cli", str(root), *args],
        input=input_text,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
        check=False,
    )


def write_reviewed_plan(root: Path) -> Path:
    path = root / "AI_Review" / "review_sessions" / "reviewed_plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(original_plan_text(), encoding="utf-8")
    return path


def original_plan_text() -> str:
    data = {
        "schema_version": 1,
        "created_at": "2026-07-10T12:00:00+00:00",
        "scan_root": ".",
        "plan_type": "batch_review",
        "summary": {},
        "items": [
            review_item("D1", "duplicate", "approved", "a.txt", "AI_Review/duplicates/a.txt"),
            review_item("O1", "organization", "rejected", "b.txt", "Organized/Notes/b.txt"),
            review_item(
                "R1",
                "review_candidate",
                "undecided",
                "c.tmp",
                "AI_Review/temporary/c.tmp",
                review_category="temporary",
            ),
        ],
    }
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def write_conflicted_plan(root: Path) -> Path:
    path = root / "AI_Review" / "review_sessions" / "conflicted.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "created_at": "2026-07-10T12:00:00+00:00",
        "scan_root": ".",
        "plan_type": "batch_review",
        "summary": {},
        "items": [
            review_item("D1", "duplicate", "approved", "shared.txt", "AI_Review/duplicates/shared.txt"),
            review_item("O1", "organization", "approved", "shared.txt", "Organized/one.txt"),
            review_item("O2", "organization", "approved", "other.txt", "Organized/shared.txt"),
            review_item(
                "R1",
                "review_candidate",
                "approved",
                "candidate.tmp",
                "Organized/shared.txt",
                review_category="temporary",
            ),
        ],
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def review_item(
    item_id: str,
    category: str,
    decision: str,
    source: str,
    destination: str,
    *,
    review_category: str | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "id": item_id,
        "category": category,
        "decision": decision,
        "source": source,
        "destination": destination,
        "reason": "test review row",
        "confidence": 100,
        "operation": "dry-run move",
        "overwrite_risk": False,
        "memory_status": "new_suggestion",
        "remembered_decision": None,
    }
    if review_category is not None:
        item["review_category"] = review_category
    return item


if __name__ == "__main__":
    unittest.main()
