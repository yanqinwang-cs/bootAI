from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from organizer.executor import apply_move_plan, undo_operation_log
from organizer.models import MovePlanItem
from organizer.organization_verify import verify_organization_apply


class OrganizationApplyVerificationTests(unittest.TestCase):
    def test_valid_apply_result_matches_filesystem_and_operation_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apply_result = make_completed_apply(root)

            outcome = verify_organization_apply(apply_result, root)
            report = read_json(outcome.result_path)

            self.assertTrue(outcome.passed)
            self.assertEqual(outcome.status, "passed")
            self.assertEqual(report["verified_destination_count"], 1)
            self.assertEqual(report["verified_missing_source_count"], 1)
            self.assertEqual(
                report["operation_log_file"],
                read_json(apply_result)["undo_log_path"],
            )

    def test_filesystem_mismatch_is_reported_without_movement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apply_result = make_completed_apply(root)
            destination = root / "Organized" / "Course" / "notes" / "a.pdf"
            destination.unlink()
            source = root / "a.pdf"
            source.write_text("returned manually", encoding="utf-8")

            outcome = verify_organization_apply(apply_result, root)
            report = read_json(outcome.result_path)

            self.assertFalse(outcome.passed)
            self.assertEqual(outcome.status, "mismatches")
            self.assertTrue(any("source still exists" in item for item in report["mismatches"]))
            self.assertTrue(any("destination is missing" in item for item in report["mismatches"]))
            self.assertEqual(source.read_text(encoding="utf-8"), "returned manually")

    def test_operation_log_pair_mismatch_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apply_result = make_completed_apply(root)
            result = read_json(apply_result)
            operation_log = root / result["undo_log_path"]
            log = read_json(operation_log)
            log["operations"][0]["destination"] = str(
                root / "Organized" / "Course" / "notes" / "other.pdf"
            )
            write_json(operation_log, log, overwrite=True)

            outcome = verify_organization_apply(apply_result, root)
            report = read_json(outcome.result_path)

            self.assertEqual(outcome.status, "mismatches")
            self.assertTrue(any("missing from operation log" in item for item in report["mismatches"]))

    def test_duplicate_applied_source_is_a_verification_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apply_result = make_completed_apply(root)
            result = read_json(apply_result)
            duplicate = dict(result["applied"][0])
            duplicate["review_id"] = "org-000002"
            duplicate["destination"] = "Organized/Course/notes/b.pdf"
            result["applied"].append(duplicate)
            result["applied_count"] = 2
            result["approved_count"] = 2
            write_json(apply_result, result, overwrite=True)

            outcome = verify_organization_apply(apply_result, root)
            report = read_json(outcome.result_path)

            self.assertEqual(outcome.status, "mismatches")
            self.assertIn("duplicate applied source: a.pdf", report["mismatches"])

    def test_malformed_apply_result_writes_invalid_input_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apply_result = root / "AI_Review" / "reviews" / "bad.json"
            apply_result.parent.mkdir(parents=True)
            apply_result.write_text("not json", encoding="utf-8")

            outcome = verify_organization_apply(apply_result, root)
            report = read_json(outcome.result_path)

            self.assertEqual(outcome.status, "invalid_input")
            self.assertFalse(report["passed"])
            self.assertTrue(report["mismatches"])

    def test_missing_operation_log_writes_invalid_input_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apply_result = write_apply_result(
                root,
                "AI_Review/operation_logs/missing.json",
            )

            outcome = verify_organization_apply(apply_result, root)

            self.assertEqual(outcome.status, "invalid_input")
            self.assertIn(
                "referenced operation log does not exist",
                read_json(outcome.result_path)["mismatches"][0],
            )

    def test_outside_root_and_direct_symlink_inputs_are_rejected_without_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            outside_result = Path(outside) / "result.json"
            outside_result.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_organization_apply(outside_result, root)
            self.assertFalse((root / "AI_Review").exists())

            if not hasattr(os, "symlink"):
                return
            link = root / "result-link.json"
            try:
                link.symlink_to(outside_result)
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, "symlink"):
                verify_organization_apply(link, root)
            self.assertFalse((root / "AI_Review").exists())

    def test_verification_output_is_collision_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apply_result = make_completed_apply(root)

            first = verify_organization_apply(apply_result, root)
            second = verify_organization_apply(apply_result, root)

            self.assertEqual(
                first.result_path.name,
                "organization_review_apply_verification.json",
            )
            self.assertEqual(
                second.result_path.name,
                "organization_review_apply_verification_1.json",
            )

    def test_cli_verification_is_single_purpose_and_reports_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apply_result = make_completed_apply(root)

            result = run_cli(
                root,
                "--verify-organization-apply",
                str(apply_result),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Verification passed", result.stdout)

            incompatible = run_cli(
                root,
                "--verify-organization-apply",
                str(apply_result),
                "--max-depth",
                "1",
            )
            self.assertNotEqual(incompatible.returncode, 0)

    def test_undo_restores_verified_apply_and_writes_result_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apply_result = make_completed_apply(root)
            verification = verify_organization_apply(apply_result, root)
            self.assertTrue(verification.passed)
            operation_log = root / read_json(apply_result)["undo_log_path"]

            undo = undo_operation_log(operation_log, root)

            self.assertTrue(all(item.success for item in undo.operations))
            self.assertTrue((root / "a.pdf").is_file())
            self.assertFalse(
                (root / "Organized" / "Course" / "notes" / "a.pdf").exists()
            )
            self.assertTrue(undo.log_path.is_file())

    def test_undo_source_collision_and_root_escape_do_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            apply_result = make_completed_apply(root)
            operation_log = root / read_json(apply_result)["undo_log_path"]
            source = root / "a.pdf"
            source.write_text("existing", encoding="utf-8")

            undo = undo_operation_log(operation_log, root)
            self.assertFalse(undo.operations[0].success)
            self.assertEqual(source.read_text(encoding="utf-8"), "existing")

            unsafe_log = root / "AI_Review" / "operation_logs" / "unsafe.json"
            write_json(
                unsafe_log,
                {
                    "operations": [
                        {
                            "source": str(Path(outside) / "source.pdf"),
                            "destination": str(root / "destination.pdf"),
                            "success": True,
                            "message": "moved",
                        }
                    ]
                },
            )
            with self.assertRaisesRegex(ValueError, "outside root"):
                undo_operation_log(unsafe_log, root)
            self.assertFalse((Path(outside) / "source.pdf").exists())

    def test_verifier_has_no_movement_dependency(self) -> None:
        module = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "organizer"
            / "organization_verify.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("organizer.exec" + "utor", module)
        for forbidden in (
            "shutil." + "move",
            ".re" + "name(",
            "un" + "link(",
            "rem" + "ove(",
            "rm" + "dir(",
            "send2" + "trash",
        ):
            self.assertNotIn(forbidden, module)

    def test_documentation_sample_and_schema_are_valid(self) -> None:
        docs = Path(__file__).resolve().parents[1] / "docs"
        sample = read_json(
            docs / "examples" / "sample_organization_review_apply_verification.json"
        )
        schema = read_json(
            docs / "schemas" / "organization_review_apply_verification.schema.json"
        )
        self.assertEqual(sample["schema_version"], 1)
        self.assertEqual(sample["status"], "passed")
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)


def make_completed_apply(root: Path) -> Path:
    source = root / "a.pdf"
    source.write_text("content", encoding="utf-8")
    destination = root / "Organized" / "Course" / "notes" / "a.pdf"
    plan = MovePlanItem(
        source=source,
        destination=destination,
        reason="approved organization review row",
        confidence=80,
        operation="dry-run move",
        overwrite_risk=False,
    )
    operation_log = apply_move_plan([plan], root)
    return write_apply_result(
        root,
        operation_log.log_path.relative_to(root.resolve()).as_posix(),
    )


def write_apply_result(root: Path, undo_log_path: str) -> Path:
    path = root / "AI_Review" / "reviews" / "organization_review_apply_result.json"
    data = {
        "schema_version": 1,
        "source": "bootAI Stage 10.9 organization review apply result",
        "generated_at": "2026-07-10T12:30:00+00:00",
        "review_file": "AI_Review/reviews/organization_review.approved.json",
        "confirmation": "APPLY ORGANIZATION REVIEW",
        "approved_count": 1,
        "applied_count": 1,
        "skipped_count": 0,
        "failed_count": 0,
        "undo_log_path": undo_log_path,
        "applied": [
            {
                "review_id": "org-000001",
                "source": "a.pdf",
                "destination": "Organized/Course/notes/a.pdf",
                "anchor": "Course",
                "risk_level": "low",
            }
        ],
        "skipped": [],
        "failed": [],
        "warnings": [],
    }
    write_json(path, data)
    return path


def write_json(path: Path, data: object, *, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    with path.open(mode, encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)
        file.write("\n")


def read_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    assert isinstance(data, dict)
    return data


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, "-m", "organizer.cli", str(root), *args],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()
