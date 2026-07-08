from pathlib import Path
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from organizer.executor import apply_move_plan
from organizer.models import MoveResult, OperationLog
from organizer.review_session import (
    approve_items,
    approved_plan_items,
    build_review_session_items,
    get_item,
    reject_items,
    save_reviewed_plan,
    summarize_review_items,
)
from organizer.scanner import scan_directory


class ReviewSessionConstructionTests(unittest.TestCase):
    def test_duplicate_and_organization_rows_are_built_from_existing_plans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)

            items = build_review_session_items(scan_directory(root), root)

            self.assertTrue(any(item.id == "D1" for item in items))
            self.assertTrue(any(item.id == "O1" for item in items))
            self.assertTrue(all(item.decision == "approved" for item in items))
            self.assertTrue(
                all(item.plan_item.operation == "dry-run move" for item in items)
            )

    def test_row_ids_are_stable_and_distinct_by_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)

            items = build_review_session_items(scan_directory(root), root)
            duplicate_ids = [item.id for item in items if item.category == "duplicate"]
            organization_ids = [item.id for item in items if item.category == "organization"]

            self.assertEqual(duplicate_ids, sorted(duplicate_ids))
            self.assertEqual(organization_ids, sorted(organization_ids))
            self.assertTrue(all(item_id.startswith("D") for item_id in duplicate_ids))
            self.assertTrue(all(item_id.startswith("O") for item_id in organization_ids))
            self.assertEqual(len({item.id for item in items}), len(items))

    def test_ai_review_files_are_not_included_in_organization_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)
            review_file = root / "AI_Review" / "notes" / "evosim_hidden.txt"
            review_file.parent.mkdir(parents=True)
            review_file.write_text("hidden", encoding="utf-8")

            items = build_review_session_items(scan_directory(root), root)
            organization_sources = [
                item.plan_item.source
                for item in items
                if item.category == "organization"
            ]

            self.assertNotIn(review_file.resolve(), organization_sources)

    def test_construction_does_not_move_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)

            build_review_session_items(scan_directory(root), root)

            self.assertTrue((root / "a.txt").exists())
            self.assertTrue((root / "subdir" / "b.txt").exists())
            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertFalse((root / "Organized").exists())
            self.assertFalse((root / "AI_Review" / "duplicates").exists())


class ReviewSessionDecisionTests(unittest.TestCase):
    def test_reject_and_approve_update_selected_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)
            items = build_review_session_items(scan_directory(root), root)

            rejected = reject_items(items, ["D1", "O1"])
            approved = approve_items(rejected, ["D1"])

            self.assertEqual(get_item(rejected, "D1").decision, "rejected")
            self.assertEqual(get_item(rejected, "O1").decision, "rejected")
            self.assertEqual(get_item(approved, "D1").decision, "approved")
            self.assertEqual(get_item(approved, "O1").decision, "rejected")

    def test_unknown_id_is_rejected_without_partial_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)
            items = build_review_session_items(scan_directory(root), root)

            with self.assertRaises(ValueError):
                reject_items(items, ["D1", "Z9"])

            self.assertEqual(get_item(items, "D1").decision, "approved")

    def test_details_and_summary_are_useful(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)
            items = reject_items(
                build_review_session_items(scan_directory(root), root),
                ["D1"],
            )

            detail = get_item(items, "D1")
            summary = summarize_review_items(items)

            self.assertEqual(detail.category, "duplicate")
            self.assertIn("exact duplicate", detail.plan_item.reason)
            self.assertEqual(summary["duplicate_rejected_move_count"], 1)
            self.assertGreaterEqual(summary["organization_approved_move_count"], 1)


class ReviewSessionSaveTests(unittest.TestCase):
    def test_save_writes_reviewed_plan_json_under_review_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)
            items = reject_items(
                build_review_session_items(scan_directory(root), root),
                ["D1"],
            )

            path = save_reviewed_plan(items, root)
            data = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(path.parent, root.resolve() / "AI_Review" / "review_sessions")
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["scan_root"], ".")
            self.assertEqual(data["plan_type"], "batch_review")
            self.assertEqual(data["summary"]["duplicate_rejected_move_count"], 1)
            self.assertIn("rejected", {item["decision"] for item in data["items"]})
            self.assertIn("approved", {item["decision"] for item in data["items"]})
            for item in data["items"]:
                self.assertFalse(Path(item["source"]).is_absolute())
                self.assertFalse(Path(item["destination"]).is_absolute())

    def test_save_does_not_overwrite_existing_reviewed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)
            items = build_review_session_items(scan_directory(root), root)
            first = save_reviewed_plan(items, root)

            with mock.patch("organizer.review_session._next_reviewed_plan_path", return_value=first):
                with self.assertRaises(ValueError):
                    save_reviewed_plan(items, root)

    def test_save_does_not_move_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)
            items = build_review_session_items(scan_directory(root), root)

            save_reviewed_plan(items, root)

            self.assertTrue((root / "a.txt").exists())
            self.assertTrue((root / "subdir" / "b.txt").exists())
            self.assertTrue((root / "evosim_notes.txt").exists())


class ReviewSessionCliTests(unittest.TestCase):
    def test_review_plans_rejects_incompatible_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)

            report_result = run_cli(root, "--review-plans", "--report")
            undo_result = run_cli(root, "--review-plans", "--undo-log", str(root / "log.json"))

            self.assertNotEqual(report_result.returncode, 0)
            self.assertNotEqual(undo_result.returncode, 0)
            self.assertIn("--review-plans cannot be combined", undo_result.stderr)

    def test_review_plans_allows_max_depth_and_scripted_save_quit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)

            result = run_cli(
                root,
                "--review-plans",
                "--max-depth",
                "2",
                input_text="summary\nreject O1\nsave\nquit\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Review summary", result.stdout)
            self.assertIn("Reviewed plan saved:", result.stdout)
            self.assertTrue(list((root / "AI_Review" / "review_sessions").glob("*.json")))
            self.assertTrue((root / "evosim_notes.txt").exists())

    def test_wrong_apply_confirmation_does_not_move_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)

            result = run_cli(
                root,
                "--review-plans",
                input_text="reject O1\napply\nWRONG\nquit\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Apply refused", result.stdout)
            self.assertTrue((root / "a.txt").exists())
            self.assertTrue((root / "evosim_notes.txt").exists())

    def test_confirmed_apply_calls_executor_with_only_approved_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)
            captured_plan_items = []

            def fake_apply(plan_items, apply_root):
                captured_plan_items.extend(plan_items)
                return OperationLog(
                    log_path=apply_root / "AI_Review" / "operation_logs" / "fake.json",
                    operations=[
                        MoveResult(
                            source=plan_items[0].source,
                            destination=plan_items[0].destination,
                            success=True,
                            message="moved",
                        )
                    ],
                )

            exit_code, output = run_cli_main(
                root,
                "--review-plans",
                input_text="reject O1 O2\napply\nAPPLY_REVIEWED_PLAN\n",
                apply_side_effect=fake_apply,
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("Applying approved moves from reviewed plan.", output)
            self.assertEqual(len(captured_plan_items), 1)
            self.assertIn("AI_Review/duplicates", captured_plan_items[0].destination.as_posix())

    def test_all_rejected_does_not_call_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_duplicate_only_fixture(root)

            exit_code, output = run_cli_main(
                root,
                "--review-plans",
                input_text="reject D1\napply\nquit\n",
                apply_side_effect=AssertionError("executor should not be called"),
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("No approved moves to apply.", output)
            self.assertTrue((root / "a.txt").exists())
            self.assertTrue((root / "b.txt").exists())

    def test_empty_plan_does_not_call_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "single.txt").write_text("single", encoding="utf-8")

            exit_code, output = run_cli_main(
                root,
                "--review-plans",
                input_text="apply\n",
                apply_side_effect=AssertionError("executor should not be called"),
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("No duplicate or organization move candidates", output)


def create_review_session_fixture(root: Path) -> None:
    (root / "subdir").mkdir()
    (root / "a.txt").write_text("same", encoding="utf-8")
    (root / "subdir" / "b.txt").write_text("same", encoding="utf-8")
    (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
    (root / "evosim_report.pdf").write_text("report", encoding="utf-8")


def create_duplicate_only_fixture(root: Path) -> None:
    (root / "a.txt").write_text("same", encoding="utf-8")
    (root / "b.txt").write_text("same", encoding="utf-8")


def run_cli(
    root: Path,
    *args: str,
    input_text: str = "",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [sys.executable, "-m", "organizer.cli", str(root), *args],
        input=input_text,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
    )


def run_cli_main(
    root: Path,
    *args: str,
    input_text: str,
    apply_side_effect=None,
) -> tuple[int, str]:
    from organizer import cli as cli_module

    stdout = io.StringIO()
    stdin = io.StringIO(input_text)
    argv = ["organizer.cli", str(root), *args]
    apply_mock = mock.patch("organizer.cli.apply_move_plan", side_effect=apply_side_effect)
    if apply_side_effect is None:
        apply_mock = mock.patch("organizer.cli.apply_move_plan", wraps=apply_move_plan)

    with mock.patch("sys.argv", argv):
        with mock.patch("sys.stdin", stdin):
            with mock.patch("sys.stdout", stdout):
                with apply_mock:
                    exit_code = cli_module.main()
    return exit_code, stdout.getvalue()


if __name__ == "__main__":
    unittest.main()
