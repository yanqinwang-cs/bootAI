from __future__ import annotations

from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from organizer.executor import undo_operation_log
from organizer.models import MoveResult, OperationLog
from organizer.organization_apply_review import (
    CONFIRM_APPLY_ORGANIZATION_REVIEW,
    OrganizationReviewApplyOutcome,
    apply_approved_organization_review,
)


class OrganizationReviewApplyTests(unittest.TestCase):
    def test_missing_confirmation_refuses_before_reading_review_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing.json"

            result = run_cli(root, "--apply-organization-review", str(missing))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Apply refused", result.stdout)
            self.assertNotIn("does not exist", result.stderr)
            self.assertFalse((root / "AI_Review").exists())

    def test_wrong_confirmation_refuses_before_path_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch(
                "organizer.organization_apply_review.resolve_organization_review_path"
            ) as resolve_path:
                with self.assertRaisesRegex(ValueError, "exact organization review"):
                    apply_approved_organization_review(
                        root / "missing.json",
                        root,
                        "WRONG",
                    )

            resolve_path.assert_not_called()
            self.assertFalse((root / "AI_Review").exists())

    def test_correct_confirmation_applies_only_approved_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approved_source = root / "approved.pdf"
            rejected_source = root / "rejected.pdf"
            undecided_source = root / "undecided.pdf"
            approved_source.write_text("approved", encoding="utf-8")
            rejected_source.write_text("rejected", encoding="utf-8")
            undecided_source.write_text("undecided", encoding="utf-8")
            review_path = write_review(
                root,
                [
                    review_row("org-000001", "approved.pdf", "approve"),
                    review_row("org-000002", "rejected.pdf", "reject"),
                    review_row("org-000003", "undecided.pdf", "undecided"),
                ],
            )

            outcome = apply_approved_organization_review(
                review_path,
                root,
                CONFIRM_APPLY_ORGANIZATION_REVIEW,
            )

            self.assertFalse(approved_source.exists())
            self.assertTrue(
                (root / "Organized" / "Course" / "notes" / "approved.pdf").exists()
            )
            self.assertTrue(rejected_source.exists())
            self.assertTrue(undecided_source.exists())
            self.assertEqual(outcome.approved_count, 1)
            self.assertEqual(outcome.applied_count, 1)
            self.assertEqual(outcome.skipped_count, 2)
            self.assertEqual(outcome.failed_count, 0)

    def test_conversion_passes_only_approved_move_plan_items_to_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_path = write_review(
                root,
                [
                    review_row("org-000001", "approved.pdf", "approve"),
                    review_row("org-000002", "rejected.pdf", "reject"),
                ],
            )
            captured = []

            def fake_apply(plan_items, apply_root):
                captured.extend(plan_items)
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

            with mock.patch(
                "organizer.organization_apply_review.apply_move_plan",
                side_effect=fake_apply,
            ):
                apply_approved_organization_review(
                    review_path,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0].source, root.resolve() / "approved.pdf")
            self.assertEqual(captured[0].operation, "dry-run move")

    def test_zero_approved_rows_writes_noop_result_without_operation_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_path = write_review(
                root,
                [
                    review_row("org-000001", "rejected.pdf", "reject"),
                    review_row("org-000002", "undecided.pdf", "undecided"),
                ],
            )

            with mock.patch(
                "organizer.organization_apply_review.apply_move_plan"
            ) as apply_plan:
                outcome = apply_approved_organization_review(
                    review_path,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

            apply_plan.assert_not_called()
            self.assertIsNone(outcome.operation_log)
            result = read_json(outcome.result_path)
            self.assertEqual(result["approved_count"], 0)
            self.assertEqual(result["skipped_count"], 2)
            self.assertIsNone(result["undo_log_path"])
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())

    def test_invalid_schema_and_duplicate_review_id_are_rejected_before_movement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = review_data([review_row("org-000001", "a.pdf", "approve")])
            data["schema_version"] = 2
            bad_schema = write_review_data(root, data, "bad_schema.json")

            with self.assertRaisesRegex(ValueError, "schema_version"):
                apply_approved_organization_review(
                    bad_schema,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

            duplicate = review_data(
                [
                    review_row("org-000001", "a.pdf", "approve"),
                    review_row("org-000001", "b.pdf", "approve"),
                ]
            )
            duplicate_path = write_review_data(root, duplicate, "duplicate.json")
            with self.assertRaisesRegex(ValueError, "duplicate review_id"):
                apply_approved_organization_review(
                    duplicate_path,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

            self.assertFalse(any((root / "AI_Review" / "reviews").glob("*apply_result*")))

    def test_duplicate_approved_sources_are_normalized_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [
                review_row("org-000001", "a.pdf", "approve"),
                review_row("org-000002", "./a.pdf", "approve", destination_name="b.pdf"),
            ]
            review_path = write_review(root, rows)

            with self.assertRaisesRegex(ValueError, "approved source conflict"):
                apply_approved_organization_review(
                    review_path,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

            self.assertFalse(any((root / "AI_Review" / "reviews").glob("*apply_result*")))

    def test_duplicate_approved_destinations_are_normalized_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = review_row("org-000001", "a.pdf", "approve")
            second = review_row("org-000002", "b.pdf", "approve")
            second["destination"] = "Organized/Course/notes/./a.pdf"
            review_path = write_review(root, [first, second])

            with self.assertRaisesRegex(ValueError, "approved destination conflict"):
                apply_approved_organization_review(
                    review_path,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

    def test_absolute_traversal_and_outside_paths_are_rejected(self) -> None:
        mutations = [
            ("source", "/tmp/a.pdf"),
            ("source", "../a.pdf"),
            ("destination", "/tmp/a.pdf"),
            ("destination", "Organized/../a.pdf"),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    row = review_row("org-000001", "a.pdf", "approve")
                    row[field] = value
                    review_path = write_review(root, [row])
                    with self.assertRaises(ValueError):
                        apply_approved_organization_review(
                            review_path,
                            root,
                            CONFIRM_APPLY_ORGANIZATION_REVIEW,
                        )

        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            outside_review = Path(outside) / "review.json"
            outside_review.write_text(
                json.dumps(review_data([])),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                apply_approved_organization_review(
                    outside_review,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

    def test_absolute_review_path_inside_root_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_path = write_review(root, [])

            outcome = apply_approved_organization_review(
                review_path.resolve(),
                root,
                CONFIRM_APPLY_ORGANIZATION_REVIEW,
            )

            self.assertTrue(outcome.result_path.exists())

    def test_missing_source_preflight_refuses_entire_batch_without_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "present.pdf").write_text("present", encoding="utf-8")
            review_path = write_review(
                root,
                [
                    review_row("org-000001", "present.pdf", "approve"),
                    review_row("org-000002", "missing.pdf", "approve"),
                ],
            )

            with self.assertRaisesRegex(ValueError, "source does not exist"):
                apply_approved_organization_review(
                    review_path,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

            self.assertTrue((root / "present.pdf").exists())
            self.assertFalse((root / "Organized").exists())
            self.assertFalse(any((root / "AI_Review" / "reviews").glob("*apply_result*")))

    def test_existing_destination_preflight_refuses_without_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.pdf").write_text("source", encoding="utf-8")
            destination = root / "Organized" / "Course" / "notes" / "a.pdf"
            destination.parent.mkdir(parents=True)
            destination.write_text("existing", encoding="utf-8")
            review_path = write_review(
                root,
                [review_row("org-000001", "a.pdf", "approve")],
            )

            with self.assertRaisesRegex(ValueError, "destination already exists"):
                apply_approved_organization_review(
                    review_path,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

            self.assertTrue((root / "a.pdf").exists())
            self.assertEqual(destination.read_text(encoding="utf-8"), "existing")
            self.assertFalse(any((root / "AI_Review" / "reviews").glob("*apply_result*")))

    def test_symlink_source_and_unsafe_destination_parent_are_rejected(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are not supported")
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            target = root / "target.pdf"
            target.write_text("target", encoding="utf-8")
            link = root / "link.pdf"
            try:
                link.symlink_to(target)
            except OSError as error:
                self.skipTest(f"symlink creation is not supported: {error}")
            source_review = write_review(
                root,
                [review_row("org-000001", "link.pdf", "approve")],
                "source_review.json",
            )
            with self.assertRaisesRegex(ValueError, "source is a symlink"):
                apply_approved_organization_review(
                    source_review,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

            unsafe_root = root / "Organized"
            unsafe_root.symlink_to(Path(outside), target_is_directory=True)
            destination_review = write_review(
                root,
                [review_row("org-000002", "target.pdf", "approve")],
                "destination_review.json",
            )
            with self.assertRaises(ValueError):
                apply_approved_organization_review(
                    destination_review,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )
            self.assertFalse(any(Path(outside).rglob("*")))

    def test_apply_result_uses_relative_paths_and_supports_collision_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_path = write_review(root, [])

            first = apply_approved_organization_review(
                review_path,
                root,
                CONFIRM_APPLY_ORGANIZATION_REVIEW,
            )
            second = apply_approved_organization_review(
                review_path,
                root,
                CONFIRM_APPLY_ORGANIZATION_REVIEW,
            )

            self.assertEqual(first.result_path.name, "organization_review_apply_result.json")
            self.assertEqual(second.result_path.name, "organization_review_apply_result_1.json")
            first_result = read_json(first.result_path)
            self.assertEqual(
                first_result["review_file"],
                "AI_Review/reviews/organization_review.approved.json",
            )
            self.assertIsNone(first_result["undo_log_path"])

    def test_successful_apply_writes_operation_log_and_undo_restores_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "a.pdf"
            source.write_text("content", encoding="utf-8")
            review_path = write_review(
                root,
                [review_row("org-000001", "a.pdf", "approve")],
            )

            outcome = apply_approved_organization_review(
                review_path,
                root,
                CONFIRM_APPLY_ORGANIZATION_REVIEW,
            )
            result = read_json(outcome.result_path)

            self.assertIsNotNone(outcome.operation_log)
            assert outcome.operation_log is not None
            self.assertTrue(outcome.operation_log.log_path.exists())
            self.assertEqual(
                result["undo_log_path"],
                outcome.operation_log.log_path.relative_to(root.resolve()).as_posix(),
            )
            undo = undo_operation_log(outcome.operation_log.log_path, root)
            self.assertTrue(all(operation.success for operation in undo.operations))
            self.assertTrue(source.exists())

    def test_partial_runtime_failure_writes_clear_counts_and_skips_unattempted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_path = write_review(
                root,
                [
                    review_row("org-000001", "a.pdf", "approve"),
                    review_row("org-000002", "b.pdf", "approve"),
                    review_row("org-000003", "c.pdf", "approve"),
                    review_row("org-000004", "d.pdf", "reject"),
                ],
            )
            fake_log = OperationLog(
                log_path=root / "AI_Review" / "operation_logs" / "partial.json",
                operations=[
                    MoveResult(
                        source=root / "a.pdf",
                        destination=root / "Organized" / "Course" / "notes" / "a.pdf",
                        success=True,
                        message="moved",
                    ),
                    MoveResult(
                        source=root / "b.pdf",
                        destination=root / "Organized" / "Course" / "notes" / "b.pdf",
                        success=False,
                        message="move failed: simulated",
                    ),
                ],
            )

            with mock.patch(
                "organizer.organization_apply_review.apply_move_plan",
                return_value=fake_log,
            ):
                outcome = apply_approved_organization_review(
                    review_path,
                    root,
                    CONFIRM_APPLY_ORGANIZATION_REVIEW,
                )

            result = read_json(outcome.result_path)
            self.assertEqual(outcome.approved_count, 3)
            self.assertEqual(outcome.applied_count, 1)
            self.assertEqual(outcome.failed_count, 1)
            self.assertEqual(outcome.skipped_count, 2)
            self.assertEqual(result["failed"][0]["review_id"], "org-000002")
            self.assertEqual(result["skipped"][-1]["review_id"], "org-000003")
            self.assertTrue(result["warnings"])

    def test_cli_confirmed_apply_and_partial_failure_reporting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_path = write_review(root, [])
            result = run_cli(
                root,
                "--apply-organization-review",
                str(review_path),
                "--confirm",
                CONFIRM_APPLY_ORGANIZATION_REVIEW,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("No approved organization review rows to apply", result.stdout)

            fake_log = OperationLog(
                log_path=root / "AI_Review" / "operation_logs" / "fake.json",
                operations=[
                    MoveResult(
                        source=root / "a.pdf",
                        destination=root / "Organized" / "a.pdf",
                        success=False,
                        message="move failed: simulated",
                    )
                ],
            )
            fake_outcome = OrganizationReviewApplyOutcome(
                result_path=root / "AI_Review" / "reviews" / "result.json",
                operation_log=fake_log,
                approved_count=1,
                applied_count=0,
                skipped_count=0,
                failed_count=1,
                warnings=(),
            )
            argv = [
                "organizer.cli",
                str(root),
                "--apply-organization-review",
                str(review_path),
                "--confirm",
                CONFIRM_APPLY_ORGANIZATION_REVIEW,
            ]
            with mock.patch("sys.argv", argv), mock.patch(
                "organizer.cli.apply_approved_organization_review",
                return_value=fake_outcome,
            ), mock.patch("sys.stdout", new_callable=io.StringIO) as output:
                from organizer.cli import main

                exit_code = main()

            self.assertEqual(exit_code, 1)
            self.assertIn("Apply completed with failures.", output.getvalue())
            self.assertNotIn("Apply completed.\n", output.getvalue())

    def test_cli_rejects_incompatible_modes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_path = write_review(root, [])
            combinations = [
                ("--max-depth", "1"),
                ("--report",),
                ("--html-report",),
                ("--export-organization-review",),
                ("--export-rule-candidates",),
                ("--apply-rule-decisions", "rules.json"),
                ("--apply-duplicate-plan",),
                ("--undo-log", "log.json"),
                ("--refine-groups", "--llm-provider", "ollama", "--llm-model", "x"),
            ]
            for combination in combinations:
                with self.subTest(combination=combination):
                    result = run_cli(
                        root,
                        "--apply-organization-review",
                        str(review_path),
                        "--confirm",
                        CONFIRM_APPLY_ORGANIZATION_REVIEW,
                        *combination,
                    )
                    self.assertNotEqual(result.returncode, 0)

    def test_apply_does_not_modify_organization_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules = root / "AI_Review" / "config" / "organization_rules.json"
            rules.parent.mkdir(parents=True)
            rules.write_text('{"version": 1}\n', encoding="utf-8")
            before = rules.read_text(encoding="utf-8")
            review_path = write_review(root, [])

            apply_approved_organization_review(
                review_path,
                root,
                CONFIRM_APPLY_ORGANIZATION_REVIEW,
            )

            self.assertEqual(rules.read_text(encoding="utf-8"), before)

    def test_module_uses_only_the_approved_movement_dependency(self) -> None:
        module = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "organizer"
            / "organization_apply_review.py"
        ).read_text(encoding="utf-8")

        self.assertIn("from organizer.exec" + "utor import apply_move_plan", module)
        for forbidden in [
            "shutil." + "move",
            "Path." + "rename",
            "os." + "rename",
            "un" + "link(",
            "rem" + "ove(",
            "rm" + "dir(",
            "send2" + "tr" + "ash",
        ]:
            self.assertNotIn(forbidden, module)

    def test_apply_result_sample_and_schema_are_valid_json(self) -> None:
        docs = Path(__file__).resolve().parents[1] / "docs"
        sample = read_json(
            docs / "examples" / "sample_organization_review_apply_result.json"
        )
        schema = read_json(
            docs / "schemas" / "organization_review_apply_result.schema.json"
        )

        self.assertEqual(sample["schema_version"], 1)
        self.assertEqual(
            sample["confirmation"],
            CONFIRM_APPLY_ORGANIZATION_REVIEW,
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)


def review_row(
    review_id: str,
    source: str,
    decision: str,
    destination_name: str | None = None,
) -> dict[str, object]:
    name = destination_name or Path(source).name
    return {
        "review_id": review_id,
        "source": source,
        "destination": f"Organized/Course/notes/{name}",
        "anchor": "Course",
        "evidence": "locked_anchor",
        "reason": "files share locked anchor Course; suggested subfolder notes",
        "confidence": 80,
        "risk_level": "low",
        "overwrite_risk": False,
        "decision": decision,
        "note": "",
    }


def review_data(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": "bootAI Stage 10.8 rule-aware organization review",
        "generated_at": "2026-07-10T12:00:00+00:00",
        "scan_root": ".",
        "instructions": (
            "Review each organization suggestion. Set decision to approve, reject, "
            "or undecided. Applying approved movement requires a later explicit "
            "confirmation step."
        ),
        "rules_loaded": False,
        "rules_path": None,
        "rule_audit_summary": {
            "locked_anchors": [],
            "preferred_granularities": [],
            "warnings": [],
        },
        "items": items,
    }


def write_review(
    root: Path,
    items: list[dict[str, object]],
    name: str = "organization_review.approved.json",
) -> Path:
    return write_review_data(root, review_data(items), name)


def write_review_data(root: Path, data: dict[str, object], name: str) -> Path:
    path = root / "AI_Review" / "reviews" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, "-m", "organizer.cli", str(root), *arguments],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()
