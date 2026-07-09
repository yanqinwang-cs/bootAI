from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from organizer.reports import build_scan_report, write_report

REPORT_TOP_LEVEL_KEYS = {
    "schema_version",
    "generated_at",
    "scan_root",
    "summary",
    "duplicates",
    "duplicate_review_plan",
    "review_candidates",
    "review_candidate_plan",
    "project_groups",
    "organization_suggestions",
    "refined_organization_suggestions",
    "warnings",
}


class ReportGenerationTests(unittest.TestCase):
    def test_report_generation_is_read_only_except_report_file_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            report = build_scan_report(root)
            report_path = write_report(report, root)

            self.assertTrue(report_path.exists())
            self.assertTrue((root / "a.txt").exists())
            self.assertTrue((root / "subdir" / "b.txt").exists())
            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertFalse((root / "Organized").exists())
            self.assertTrue((root / "AI_Review" / "reports").exists())

    def test_report_contains_required_shape_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            report = build_scan_report(root)

            self.assertEqual(report["schema_version"], 1)
            self.assertIn("generated_at", report)
            self.assertEqual(report["scan_root"], ".")
            self.assertIn("summary", report)
            summary = report["summary"]
            for key in [
                "file_count",
                "total_bytes",
                "duplicate_group_count",
                "duplicate_candidate_count",
                "review_candidate_count",
                "review_candidate_counts_by_category",
                "project_group_count",
                "organization_suggestion_count",
                "refinement_status",
            ]:
                self.assertIn(key, summary)
            for key in [
                "duplicates",
                "duplicate_review_plan",
                "review_candidates",
                "review_candidate_plan",
                "project_groups",
                "organization_suggestions",
                "refined_organization_suggestions",
                "warnings",
            ]:
                self.assertIn(key, report)

    def test_report_details_include_expected_sections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            report = build_scan_report(root)

            self.assertEqual(report["summary"]["duplicate_group_count"], 1)
            self.assertEqual(report["summary"]["duplicate_candidate_count"], 1)
            self.assertGreaterEqual(report["summary"]["review_candidate_count"], 1)
            self.assertIn("empty", report["summary"]["review_candidate_counts_by_category"])
            self.assertGreaterEqual(report["summary"]["project_group_count"], 1)
            self.assertGreaterEqual(report["summary"]["organization_suggestion_count"], 1)
            self.assertEqual(report["summary"]["refinement_status"], "not_requested")
            self.assertEqual(report["duplicates"][0]["files"], ["a.txt", "subdir/b.txt"])
            self.assertIn("source", report["duplicate_review_plan"][0])
            self.assertIn("destination", report["organization_suggestions"][0]["plan_items"][0])

    def test_report_includes_orphan_code_candidate_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "practice.py").write_text("print('x')", encoding="utf-8")

            report = build_scan_report(root)

            self.assertEqual(report["summary"]["review_candidate_count"], 1)
            self.assertEqual(
                report["summary"]["review_candidate_counts_by_category"]["orphan_code"],
                1,
            )
            self.assertEqual(report["review_candidates"][0]["category"], "orphan_code")

    def test_excessive_organization_suggestion_warning_is_added(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["evosim_notes.txt", "evosim_report.pdf", "other.pdf"]:
                (root / name).write_text("document", encoding="utf-8")

            report = build_scan_report(root)

            self.assertGreater(report["summary"]["organization_suggestion_count"], 0)
            self.assertTrue(
                any("Organization suggestions are unusually broad" in warning for warning in report["warnings"])
            )


class ReportOutputSafetyTests(unittest.TestCase):
    def test_default_report_writes_under_review_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            report_path = write_report(build_scan_report(root), root)

            self.assertEqual(report_path.parent, root.resolve() / "AI_Review" / "reports")
            self.assertTrue(report_path.name.endswith("_report.json"))

    def test_custom_report_output_under_root_works(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)
            custom_output = root / "AI_Review" / "reports" / "custom.json"

            report_path = write_report(build_scan_report(root), root, custom_output)

            self.assertEqual(report_path, custom_output.resolve())
            self.assertTrue(custom_output.exists())

    def test_relative_custom_report_output_is_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            report_path = write_report(
                build_scan_report(root),
                root,
                Path("AI_Review/reports/relative.json"),
            )

            self.assertEqual(report_path, root.resolve() / "AI_Review" / "reports" / "relative.json")
            self.assertTrue(report_path.exists())

    def test_custom_report_output_outside_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            root.mkdir()
            create_report_fixture(root)
            outside_output = base / "outside.json"

            with self.assertRaises(ValueError):
                write_report(build_scan_report(root), root, outside_output)

            self.assertFalse(outside_output.exists())

    def test_existing_report_file_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)
            output = root / "AI_Review" / "reports" / "existing.json"
            output.parent.mkdir(parents=True)
            output.write_text("existing", encoding="utf-8")

            with self.assertRaises(ValueError):
                write_report(build_scan_report(root), root, output)

            self.assertEqual(output.read_text(encoding="utf-8"), "existing")

    def test_symlinked_output_path_escaping_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            create_report_fixture(root)
            link = root / "AI_Review"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("Symlinks are not supported on this OS or filesystem")

            with self.assertRaises(ValueError):
                write_report(
                    build_scan_report(root),
                    root,
                    root / "AI_Review" / "reports" / "report.json",
                )

            self.assertFalse((outside / "reports" / "report.json").exists())


class ReportNoMovementTests(unittest.TestCase):
    def test_report_mode_does_not_move_duplicate_or_organization_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            result = run_cli(root, "--report")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "a.txt").exists())
            self.assertTrue((root / "subdir" / "b.txt").exists())
            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertFalse((root / "Organized").exists())
            self.assertFalse((root / "AI_Review" / "duplicates").exists())

    def test_report_mode_does_not_call_executor_apply_move_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)
            from organizer import cli as cli_module

            with mock.patch("sys.argv", ["organizer.cli", str(root), "--report"]):
                with mock.patch("sys.stdout"):
                    with mock.patch("organizer.cli.apply_move_plan") as mocked_apply:
                        exit_code = cli_module.main()

            self.assertEqual(exit_code, 0)
            mocked_apply.assert_not_called()


class ReportCliTests(unittest.TestCase):
    def test_cli_report_writes_report_and_prints_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            result = run_cli(root, "--report")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Report written:", result.stdout)
            report_path = extract_report_path(result.stdout)
            self.assertTrue(report_path.exists())
            data = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], 1)

    def test_cli_report_output_writes_custom_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)
            output = root / "AI_Review" / "reports" / "custom.json"

            result = run_cli(root, "--report", "--report-output", str(output))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(output), result.stdout)
            self.assertTrue(output.exists())

    def test_cli_report_refuses_undo_combination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            result = run_cli(root, "--report", "--undo-log", str(root / "log.json"))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--report cannot be combined", result.stderr)
            self.assertFalse((root / "AI_Review").exists())

    def test_cli_report_refuses_apply_and_confirm_combination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            apply_result = run_cli(root, "--report", "--apply-organization-plan")
            confirm_result = run_cli(root, "--report", "--confirm", "APPLY_ORGANIZATION_PLAN")

            self.assertNotEqual(apply_result.returncode, 0)
            self.assertNotEqual(confirm_result.returncode, 0)
            self.assertFalse((root / "Organized").exists())

    def test_existing_apply_confirmation_behavior_still_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")

            refused = run_cli(root, "--apply-duplicate-plan")
            applied = run_cli(
                root,
                "--apply-duplicate-plan",
                "--confirm",
                "APPLY_DUPLICATE_PLAN",
            )

            self.assertEqual(refused.returncode, 0, refused.stderr)
            self.assertIn("Apply refused", refused.stdout)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertFalse((root / "b.txt").exists())


class ReportLlmTests(unittest.TestCase):
    def test_mocked_valid_refinement_appears_in_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)
            client = FakeClient()

            report = build_scan_report(root, refine_groups=True, llm_client=client)

            self.assertEqual(report["summary"]["refinement_status"], "completed")
            self.assertEqual(report["warnings"], [])
            self.assertTrue(report["refined_organization_suggestions"])

    def test_mocked_invalid_refinement_produces_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            report = build_scan_report(
                root,
                refine_groups=True,
                llm_client=FakeClient(response_text="not json"),
            )

            self.assertEqual(report["summary"]["refinement_status"], "failed")
            self.assertEqual(report["refined_organization_suggestions"], [])
            self.assertTrue(report["warnings"])


class ReportDocumentationTests(unittest.TestCase):
    def test_sample_report_is_valid_json_with_expected_top_level_keys(self) -> None:
        sample_path = repository_root() / "docs" / "examples" / "sample_report.json"

        sample = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertEqual(set(sample), REPORT_TOP_LEVEL_KEYS)
        self.assertEqual(sample["schema_version"], 1)
        self.assertEqual(sample["scan_root"], ".")

    def test_sample_report_uses_relative_paths(self) -> None:
        sample_path = repository_root() / "docs" / "examples" / "sample_report.json"
        sample = json.loads(sample_path.read_text(encoding="utf-8"))

        paths = collect_report_paths(sample)

        self.assertTrue(paths)
        for path in paths:
            self.assertFalse(Path(path).is_absolute(), path)
            self.assertNotIn("/Users/", path)

    def test_report_schema_reference_is_valid_json(self) -> None:
        schema_path = repository_root() / "docs" / "schemas" / "report.schema.json"

        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(set(schema["required"]), REPORT_TOP_LEVEL_KEYS)
        self.assertIn("documentation-only", schema["description"].lower())


class FakeClient:
    def __init__(self, response_text: str | None = None):
        self.response_text = response_text

    def chat(self, messages):
        payload = json.loads(messages[-1]["content"].split("Payload: ", 1)[1])
        if self.response_text is not None:
            return self.response_text
        return json.dumps(
            {
                "folder_name": f"{payload['group_name']}_Refined",
                "confidence": 80,
                "reason": "suggested grouping based on provided paths",
                "subfolders": {
                    file["relative_path"]: file["deterministic_subfolder"]
                    for file in payload["files"]
                },
                "warnings": [],
            }
        )


def create_report_fixture(root: Path) -> None:
    (root / "subdir").mkdir()
    (root / "a.txt").write_text("same", encoding="utf-8")
    (root / "subdir" / "b.txt").write_text("same", encoding="utf-8")
    (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
    (root / "evosim_report.pdf").write_text("report", encoding="utf-8")
    (root / "empty_candidate.txt").write_text("", encoding="utf-8")


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [sys.executable, "-m", "organizer.cli", str(root), *args],
        check=False,
        cwd=repository_root(),
        env=env,
        capture_output=True,
        text=True,
    )


def extract_report_path(output: str) -> Path:
    for line in output.splitlines():
        if line.startswith("Report written: "):
            return Path(line.removeprefix("Report written: "))
        if line.startswith("Report written with warnings: "):
            return Path(line.removeprefix("Report written with warnings: "))
    raise AssertionError("report path not found in CLI output")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def collect_report_paths(value) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"path", "source", "destination", "suggested_root"} and isinstance(child, str):
                paths.append(child)
            elif key == "files" and isinstance(child, list):
                paths.extend(item for item in child if isinstance(item, str))
            else:
                paths.extend(collect_report_paths(child))
    elif isinstance(value, list):
        for child in value:
            paths.extend(collect_report_paths(child))
    return paths


if __name__ == "__main__":
    unittest.main()
