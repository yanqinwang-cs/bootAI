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

from organizer.models import MovePlanItem
from organizer.review_session import (
    approve_items,
    find_approved_move_conflicts,
    load_reviewed_plan_items,
    load_reviewed_plan_move_items,
    reject_items,
    save_resumed_reviewed_plan,
    undecide_items,
)


class ResumeReviewedPlanTests(unittest.TestCase):
    def test_valid_session_preserves_decisions_ids_and_metadata_without_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_reviewed_plan(root, reviewed_plan_data())

            with mock.patch(
                "organizer.review_session.scan_directory",
                side_effect=AssertionError("resume must not scan"),
            ):
                items = load_reviewed_plan_items(path, root)

            self.assertEqual([item.id for item in items], ["D1", "O1", "R1"])
            self.assertEqual(
                [item.decision for item in items],
                ["approved", "rejected", "undecided"],
            )
            self.assertEqual(items[1].plan_item.reason, "project notes")
            self.assertEqual(items[1].plan_item.confidence, 70)
            self.assertEqual(items[2].review_category, "temporary")
            self.assertEqual(items[2].plan_item.operation, "dry-run move")

    def test_decisions_can_be_changed_including_undecided(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items = load_reviewed_plan_items(
                write_reviewed_plan(root, reviewed_plan_data()),
                root,
            )

            items = reject_items(items, ["D1"])
            items = approve_items(items, ["O1"])
            items = undecide_items(items, ["O1"])

            decisions = {item.id: item.decision for item in items}
            self.assertEqual(decisions, {
                "D1": "rejected",
                "O1": "undecided",
                "R1": "undecided",
            })

    def test_resumed_save_preserves_input_and_uses_collision_safe_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = write_reviewed_plan(root, reviewed_plan_data())
            original = source.read_text(encoding="utf-8")
            items = load_reviewed_plan_items(source, root)

            first = save_resumed_reviewed_plan(items, root, source)
            second = save_resumed_reviewed_plan(items, root, source)

            self.assertEqual(first.name, "reviewed_plan_1.json")
            self.assertEqual(second.name, "reviewed_plan_2.json")
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertEqual(
                [item["id"] for item in read_json(first)["items"]],
                ["D1", "O1", "R1"],
            )

    def test_saved_output_passes_existing_apply_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("a.txt", "notes.txt", "file.tmp"):
                (root / name).write_text("content", encoding="utf-8")
            source = write_reviewed_plan(root, reviewed_plan_data())
            items = load_reviewed_plan_items(source, root)
            output = save_resumed_reviewed_plan(items, root, source)

            plan_items = load_reviewed_plan_move_items(output, root)

            self.assertEqual(len(plan_items), 1)
            self.assertEqual(plan_items[0].source, root.resolve() / "a.txt")

    def test_approved_conflicts_remain_visible_and_rejection_resolves_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = reviewed_plan_data()
            data["items"][1]["decision"] = "approved"
            data["items"][1]["source"] = "a.txt"
            items = load_reviewed_plan_items(write_reviewed_plan(root, data), root)

            conflicts = find_approved_move_conflicts(items, root)
            resolved = reject_items(items, ["O1"])

            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].conflict_type, "source")
            self.assertEqual(find_approved_move_conflicts(resolved, root), [])

    def test_empty_saved_session_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = reviewed_plan_data()
            data["items"] = []

            items = load_reviewed_plan_items(write_reviewed_plan(root, data), root)

            self.assertEqual(items, [])

    def test_malformed_schema_missing_fields_and_invalid_decisions_are_rejected(self) -> None:
        mutations = [
            lambda data: data.update(schema_version=2),
            lambda data: data.pop("items"),
            lambda data: data["items"][0].pop("source"),
            lambda data: data["items"][0].pop("reason"),
            lambda data: data["items"][0].update(decision="maybe"),
            lambda data: data["items"][0].update(category="unknown"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                data = reviewed_plan_data()
                mutate(data)
                path = write_reviewed_plan(root, data)
                with self.assertRaises(ValueError):
                    load_reviewed_plan_items(path, root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "bad.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_reviewed_plan_items(path, root)

    def test_unsafe_paths_and_duplicate_ids_are_rejected(self) -> None:
        mutations = [
            ("source", "../outside.txt"),
            ("source", "/tmp/outside.txt"),
            ("destination", "../outside.txt"),
            ("destination", "/tmp/outside.txt"),
            ("source", "..\\outside.txt"),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                data = reviewed_plan_data()
                data["items"][0][field] = value
                with self.assertRaises(ValueError):
                    load_reviewed_plan_items(write_reviewed_plan(root, data), root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = reviewed_plan_data()
            data["items"][1]["id"] = "D1"
            with self.assertRaisesRegex(ValueError, "duplicate item ID"):
                load_reviewed_plan_items(write_reviewed_plan(root, data), root)

    def test_missing_directory_outside_and_symlink_inputs_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            outside_path = Path(outside) / "plan.json"
            outside_path.write_text(json.dumps(reviewed_plan_data()), encoding="utf-8")

            for path in (root / "missing.json", root, outside_path):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    load_reviewed_plan_items(path, root)

            if not hasattr(os, "symlink"):
                return
            link = root / "plan-link.json"
            try:
                link.symlink_to(outside_path)
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, "symlink"):
                load_reviewed_plan_items(link, root)

    def test_cli_resume_preserves_saved_decisions_and_does_not_use_review_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = write_reviewed_plan(root, reviewed_plan_data())
            state_path = root / "AI_Review" / "review_state" / "review_decisions.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text("not valid state JSON", encoding="utf-8")

            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(source),
                input_text="details O1\nsummary\nquit\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Saved decisions are authoritative", result.stdout)
            self.assertIn("decision: rejected", result.stdout)
            self.assertIn("total undecided moves: 1", result.stdout)

    def test_cli_edit_save_is_non_mutating_and_quit_without_save_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = write_reviewed_plan(root, reviewed_plan_data())
            original = source.read_text(encoding="utf-8")
            (root / "a.txt").write_text("source", encoding="utf-8")

            quit_result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(source),
                input_text="reject D1\nquit\n",
            )
            self.assertEqual(quit_result.returncode, 0, quit_result.stderr)
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertFalse(source.with_name("reviewed_plan_1.json").exists())

            save_result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(source),
                input_text="undecide D1\nsave\nquit\n",
            )
            saved = source.with_name("reviewed_plan_1.json")
            self.assertEqual(save_result.returncode, 0, save_result.stderr)
            self.assertTrue(saved.is_file())
            self.assertEqual(read_json(saved)["items"][0]["decision"], "undecided")
            self.assertTrue((root / "a.txt").is_file())
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())

    def test_cli_resume_rejects_incompatible_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = write_reviewed_plan(root, reviewed_plan_data())
            combinations = [
                ("--max-depth", "1"),
                ("--report",),
                ("--html-report",),
                ("--review-plans",),
                ("--apply-reviewed-plan", str(source)),
                ("--undo-log", "log.json"),
                ("--verify-organization-apply", "verification.json"),
                ("--confirm", "APPLY_REVIEWED_PLAN"),
            ]
            for combination in combinations:
                with self.subTest(combination=combination):
                    result = run_cli(
                        root,
                        "--resume-reviewed-plan",
                        str(source),
                        *combination,
                    )
                    self.assertNotEqual(result.returncode, 0)

    def test_interactive_apply_reuses_saved_plan_validator_after_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = write_reviewed_plan(root, reviewed_plan_data())
            expected_plan = MovePlanItem(
                source=root / "a.txt",
                destination=root / "AI_Review" / "duplicates" / "a.txt",
                reason="exact duplicate of b.txt",
                confidence=100,
                operation="dry-run move",
                overwrite_risk=False,
            )
            argv = [
                "organizer.cli",
                str(root),
                "--resume-reviewed-plan",
                str(source),
            ]
            with mock.patch("sys.argv", argv), mock.patch(
                "builtins.input",
                side_effect=["apply", "APPLY_REVIEWED_PLAN"],
            ), mock.patch(
                "organizer.cli.load_reviewed_plan_move_items",
                return_value=[expected_plan],
            ) as validate_apply, mock.patch(
                "organizer.cli._apply_plan_items",
                return_value=0,
            ) as apply_items, mock.patch(
                "sys.stdout",
                new_callable=io.StringIO,
            ):
                from organizer.cli import main

                exit_code = main()

            self.assertEqual(exit_code, 0)
            validate_apply.assert_called_once()
            validated_path = validate_apply.call_args.args[0]
            self.assertEqual(validated_path.name, "reviewed_plan_1.json")
            apply_items.assert_called_once_with([expected_plan], root)


def reviewed_plan_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "created_at": "2026-07-10T12:00:00+00:00",
        "scan_root": ".",
        "plan_type": "batch_review",
        "summary": {},
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
            },
            {
                "id": "O1",
                "category": "organization",
                "decision": "rejected",
                "source": "notes.txt",
                "destination": "Organized/Course/notes/notes.txt",
                "reason": "project notes",
                "confidence": 70,
                "operation": "dry-run move",
                "overwrite_risk": False,
            },
            {
                "id": "R1",
                "category": "review_candidate",
                "review_category": "temporary",
                "decision": "undecided",
                "source": "file.tmp",
                "destination": "AI_Review/temporary/file.tmp",
                "reason": "candidate for review",
                "confidence": 95,
                "operation": "dry-run move",
                "overwrite_risk": False,
            },
        ],
    }


def write_reviewed_plan(root: Path, data: object) -> Path:
    path = root / "AI_Review" / "review_sessions" / "reviewed_plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
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
