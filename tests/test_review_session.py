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
    load_reviewed_plan_move_items,
    reject_items,
    save_reviewed_plan,
    reviewed_plan_data_to_move_items,
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


class SavedReviewedPlanValidationTests(unittest.TestCase):
    def test_valid_saved_reviewed_plan_loads_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)
            plan_path = write_reviewed_plan(root, valid_saved_plan_data())

            plan_items = load_reviewed_plan_move_items(plan_path, root)

            self.assertEqual(len(plan_items), 1)
            self.assertEqual(plan_items[0].source, root.resolve() / "a.txt")
            self.assertEqual(plan_items[0].destination, root.resolve() / "AI_Review" / "duplicates" / "a.txt")

    def test_invalid_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "AI_Review" / "review_sessions" / "bad.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text("{", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_reviewed_plan_move_items(plan_path, root)

    def test_top_level_non_object_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            reviewed_plan_data_to_move_items([], Path("/tmp/root"))

    def test_unsupported_schema_version_is_rejected(self) -> None:
        data = valid_saved_plan_data()
        data["schema_version"] = 2

        with self.assertRaises(ValueError):
            reviewed_plan_data_to_move_items(data, Path("/tmp/root"))

    def test_wrong_plan_type_is_rejected(self) -> None:
        data = valid_saved_plan_data()
        data["plan_type"] = "other"

        with self.assertRaises(ValueError):
            reviewed_plan_data_to_move_items(data, Path("/tmp/root"))

    def test_missing_or_non_list_items_is_rejected(self) -> None:
        missing = valid_saved_plan_data()
        missing.pop("items")
        non_list = valid_saved_plan_data()
        non_list["items"] = {}

        with self.assertRaises(ValueError):
            reviewed_plan_data_to_move_items(missing, Path("/tmp/root"))
        with self.assertRaises(ValueError):
            reviewed_plan_data_to_move_items(non_list, Path("/tmp/root"))

    def test_invalid_category_and_decision_are_rejected(self) -> None:
        bad_category = valid_saved_plan_data()
        bad_category["items"][0]["category"] = "review_candidate"
        bad_decision = valid_saved_plan_data()
        bad_decision["items"][0]["decision"] = "maybe"

        with self.assertRaises(ValueError):
            reviewed_plan_data_to_move_items(bad_category, Path("/tmp/root"))
        with self.assertRaises(ValueError):
            reviewed_plan_data_to_move_items(bad_decision, Path("/tmp/root"))

    def test_absolute_paths_and_traversal_are_rejected(self) -> None:
        root = Path("/tmp/root")
        cases = [
            ("source", "/tmp/source.txt"),
            ("destination", "/tmp/destination.txt"),
            ("source", "../source.txt"),
            ("destination", "../destination.txt"),
        ]

        for field, value in cases:
            data = valid_saved_plan_data()
            data["items"][0][field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    reviewed_plan_data_to_move_items(data, root)

    def test_only_approved_items_become_move_plan_items(self) -> None:
        root = Path("/tmp/root")
        data = valid_saved_plan_data()
        data["items"].append(
            {
                "id": "O1",
                "category": "organization",
                "decision": "rejected",
                "source": "evosim_notes.txt",
                "destination": "Organized/Evosim/notes/evosim_notes.txt",
                "reason": "ignored",
                "extra": "ignored",
            }
        )

        plan_items = reviewed_plan_data_to_move_items(data, root)

        self.assertEqual(len(plan_items), 1)
        self.assertEqual(plan_items[0].source, root / "a.txt")

    def test_reason_operation_and_confidence_fallbacks(self) -> None:
        root = Path("/tmp/root")
        data = valid_saved_plan_data()
        data["items"][0]["reason"] = ""
        data["items"][0]["confidence"] = "high"
        data["items"][0]["operation"] = ""

        plan_items = reviewed_plan_data_to_move_items(data, root)

        self.assertEqual(plan_items[0].reason, "Approved reviewed plan item.")
        self.assertEqual(plan_items[0].confidence, 100)
        self.assertEqual(plan_items[0].operation, "dry-run move")

    def test_all_rejected_plan_returns_empty_move_plan(self) -> None:
        data = valid_saved_plan_data()
        data["items"][0]["decision"] = "rejected"

        plan_items = reviewed_plan_data_to_move_items(data, Path("/tmp/root"))

        self.assertEqual(plan_items, [])

    def test_plan_path_outside_root_directory_and_missing_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            outside = base / "outside.json"
            root.mkdir()
            outside.write_text(json.dumps(valid_saved_plan_data()), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_reviewed_plan_move_items(outside, root)
            with self.assertRaises(ValueError):
                load_reviewed_plan_move_items(root, root)
            with self.assertRaises(ValueError):
                load_reviewed_plan_move_items(root / "missing.json", root)

    def test_executor_rejects_missing_source_and_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_duplicate_only_fixture(root)
            destination = root / "AI_Review" / "duplicates" / "a.txt"
            destination.parent.mkdir(parents=True)
            destination.write_text("existing", encoding="utf-8")
            plan_path = write_reviewed_plan(root, valid_saved_plan_data())

            plan_items = load_reviewed_plan_move_items(plan_path, root)
            with self.assertRaises(ValueError):
                apply_move_plan(plan_items, root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = valid_saved_plan_data()
            data["items"][0]["source"] = "missing.txt"
            plan_path = write_reviewed_plan(root, data)

            plan_items = load_reviewed_plan_move_items(plan_path, root)
            with self.assertRaises(ValueError):
                apply_move_plan(plan_items, root)

    def test_executor_rejects_direct_symlink_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.txt"
            source = root / "a.txt"
            target.write_text("target", encoding="utf-8")
            try:
                source.symlink_to(target)
            except (NotImplementedError, OSError):
                self.skipTest("Symlinks are not supported on this OS or filesystem")
            plan_path = write_reviewed_plan(root, valid_saved_plan_data())

            plan_items = load_reviewed_plan_move_items(plan_path, root)
            with self.assertRaises(ValueError):
                apply_move_plan(plan_items, root)

    def test_executor_rejects_unsafe_destination_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "a.txt").write_text("same", encoding="utf-8")
            try:
                (root / "AI_Review").symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("Symlinks are not supported on this OS or filesystem")
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(valid_saved_plan_data()), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_reviewed_plan_move_items(plan_path, root)


class SavedReviewedPlanCliTests(unittest.TestCase):
    def test_apply_reviewed_plan_requires_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_duplicate_only_fixture(root)
            plan_path = write_reviewed_plan(root, valid_saved_plan_data())

            refused = run_cli(root, "--apply-reviewed-plan", str(plan_path))
            wrong = run_cli(
                root,
                "--apply-reviewed-plan",
                str(plan_path),
                "--confirm",
                "WRONG",
            )

            self.assertEqual(refused.returncode, 0, refused.stderr)
            self.assertEqual(wrong.returncode, 0, wrong.stderr)
            self.assertIn("Apply refused", wrong.stdout)
            self.assertTrue((root / "a.txt").exists())

    def test_confirmed_apply_passes_only_approved_items_to_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_review_session_fixture(root)
            data = valid_saved_plan_data()
            data["items"].append(
                {
                    "id": "O1",
                    "category": "organization",
                    "decision": "rejected",
                    "source": "evosim_notes.txt",
                    "destination": "Organized/Evosim/notes/evosim_notes.txt",
                    "reason": "ignored",
                }
            )
            plan_path = write_reviewed_plan(root, data)
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
                "--apply-reviewed-plan",
                str(plan_path),
                "--confirm",
                "APPLY_REVIEWED_PLAN",
                input_text="",
                apply_side_effect=fake_apply,
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("Applying approved moves from saved reviewed plan.", output)
            self.assertEqual(len(captured_plan_items), 1)
            self.assertEqual(captured_plan_items[0].source, root.resolve() / "a.txt")

    def test_all_rejected_saved_plan_does_not_call_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_duplicate_only_fixture(root)
            data = valid_saved_plan_data()
            data["items"][0]["decision"] = "rejected"
            plan_path = write_reviewed_plan(root, data)

            exit_code, output = run_cli_main(
                root,
                "--apply-reviewed-plan",
                str(plan_path),
                "--confirm",
                "APPLY_REVIEWED_PLAN",
                input_text="",
                apply_side_effect=AssertionError("executor should not be called"),
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("No approved moves to apply.", output)

    def test_apply_reviewed_plan_rejects_incompatible_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_duplicate_only_fixture(root)
            plan_path = write_reviewed_plan(root, valid_saved_plan_data())

            report_result = run_cli(root, "--apply-reviewed-plan", str(plan_path), "--report")
            review_result = run_cli(root, "--apply-reviewed-plan", str(plan_path), "--review-plans")
            undo_result = run_cli(
                root,
                "--apply-reviewed-plan",
                str(plan_path),
                "--undo-log",
                str(root / "log.json"),
            )

            self.assertNotEqual(report_result.returncode, 0)
            self.assertNotEqual(review_result.returncode, 0)
            self.assertNotEqual(undo_result.returncode, 0)
            self.assertIn("--apply-reviewed-plan cannot be combined", undo_result.stderr)


def create_review_session_fixture(root: Path) -> None:
    (root / "subdir").mkdir()
    (root / "a.txt").write_text("same", encoding="utf-8")
    (root / "subdir" / "b.txt").write_text("same", encoding="utf-8")
    (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
    (root / "evosim_report.pdf").write_text("report", encoding="utf-8")


def create_duplicate_only_fixture(root: Path) -> None:
    (root / "a.txt").write_text("same", encoding="utf-8")
    (root / "b.txt").write_text("same", encoding="utf-8")


def valid_saved_plan_data():
    return {
        "schema_version": 1,
        "created_at": "2026-07-09T12:00:00+00:00",
        "scan_root": ".",
        "plan_type": "batch_review",
        "summary": {
            "approved_move_count": 1,
            "rejected_move_count": 0,
            "duplicate_approved_move_count": 1,
            "duplicate_rejected_move_count": 0,
            "organization_approved_move_count": 0,
            "organization_rejected_move_count": 0,
        },
        "items": [
            {
                "id": "D1",
                "category": "duplicate",
                "decision": "approved",
                "source": "a.txt",
                "destination": "AI_Review/duplicates/a.txt",
                "reason": "exact duplicate of b.txt",
                "confidence": 100,
                "operation": "dry-run move",
                "overwrite_risk": False,
            }
        ],
    }


def write_reviewed_plan(root: Path, data) -> Path:
    path = root / "AI_Review" / "review_sessions" / "reviewed_plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


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
