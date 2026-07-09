from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from organizer.html_report import (
    html_report_output_path,
    render_html_report,
    write_html_report,
)
from organizer.reports import build_scan_report, write_report


class HtmlReportRenderingTests(unittest.TestCase):
    def test_render_html_report_contains_document_structure_and_sections(self) -> None:
        report = sample_report()

        html = render_html_report(report)

        self.assertIn("<!doctype html>", html)
        self.assertIn('<meta charset="utf-8">', html)
        self.assertIn("<title>bootAI Report</title>", html)
        self.assertIn("Summary", html)
        self.assertIn("Warnings", html)
        self.assertIn("Duplicate review plan", html)
        self.assertIn("Review candidates", html)
        self.assertIn("Review candidate plan", html)
        self.assertIn("Project groups", html)
        self.assertIn("Organization suggestions", html)
        self.assertIn("Refined organization suggestions", html)
        self.assertIn("dry-run plan item", html)
        self.assertIn("candidate for review", html.lower())
        self.assertIn("suggested move", html)

    def test_empty_sections_show_clear_empty_message(self) -> None:
        report = sample_report()
        report["warnings"] = []
        report["duplicate_review_plan"] = []
        report["review_candidates"] = []
        report["review_candidate_plan"] = []
        report["project_groups"] = []
        report["organization_suggestions"] = []
        report["refined_organization_suggestions"] = []

        html = render_html_report(report)

        self.assertGreaterEqual(html.count("No entries in this section."), 6)

    def test_dynamic_text_is_escaped(self) -> None:
        report = sample_report()
        report["warnings"] = ['<script>alert("x")</script>']
        report["review_candidates"][0]["reason"] = "<b>candidate</b>"

        html = render_html_report(report)

        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;candidate&lt;/b&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<b>candidate</b>", html)

    def test_file_contents_are_not_rendered(self) -> None:
        report = sample_report()
        report["summary"]["file_count"] = 1

        html = render_html_report(report)

        self.assertNotIn("secret file body", html)


class HtmlReportOutputTests(unittest.TestCase):
    def test_default_html_path_uses_json_report_stem(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "AI_Review" / "reports" / "example_report.json"

            html_path = html_report_output_path(root, json_report_path=json_path)

            self.assertEqual(
                html_path,
                root.resolve() / "AI_Review" / "reports" / "example_report.html",
            )

    def test_write_html_report_under_review_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "AI_Review" / "reports" / "example_report.json"

            html_path = write_html_report(sample_report(), root, json_report_path=json_path)

            self.assertEqual(html_path.parent, root.resolve() / "AI_Review" / "reports")
            self.assertTrue(html_path.name.endswith("_report.html"))
            self.assertIn("bootAI Report", html_path.read_text(encoding="utf-8"))

    def test_custom_html_output_under_root_works(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "AI_Review" / "reports" / "custom.html"

            html_path = write_html_report(sample_report(), root, output_path=output)

            self.assertEqual(html_path, output.resolve())
            self.assertTrue(output.exists())

    def test_custom_html_output_outside_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            root.mkdir()
            outside = base / "report.html"

            with self.assertRaises(ValueError):
                write_html_report(sample_report(), root, output_path=outside)

            self.assertFalse(outside.exists())

    def test_existing_html_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "AI_Review" / "reports" / "existing.html"
            output.parent.mkdir(parents=True)
            output.write_text("existing", encoding="utf-8")

            with self.assertRaises(ValueError):
                write_html_report(sample_report(), root, output_path=output)

            self.assertEqual(output.read_text(encoding="utf-8"), "existing")

    def test_symlinked_output_path_escaping_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            link = root / "AI_Review"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("Symlinks are not supported on this OS or filesystem")

            with self.assertRaises(ValueError):
                write_html_report(
                    sample_report(),
                    root,
                    output_path=root / "AI_Review" / "reports" / "report.html",
                )

            self.assertFalse((outside / "reports" / "report.html").exists())


class HtmlReportCliTests(unittest.TestCase):
    def test_cli_html_report_writes_json_and_html_and_prints_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            result = run_cli(root, "--html-report")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("HTML report written:", result.stdout)
            self.assertIn("JSON report written:", result.stdout)
            html_path = extract_path(result.stdout, "HTML report written: ")
            json_path = extract_path(result.stdout, "JSON report written: ")
            self.assertTrue(html_path.exists())
            self.assertTrue(json_path.exists())
            self.assertEqual(html_path.suffix, ".html")
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["schema_version"], 1)
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())
            self.assertTrue((root / "a.txt").exists())
            self.assertTrue((root / "subdir" / "b.txt").exists())

    def test_cli_html_report_output_writes_custom_html_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)
            output = root / "AI_Review" / "reports" / "custom.html"

            result = run_cli(root, "--html-report", "--html-report-output", str(output))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(output), result.stdout)
            self.assertTrue(output.exists())
            self.assertTrue(list((root / "AI_Review" / "reports").glob("*_report.json")))

    def test_cli_html_report_rejects_incompatible_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            cases = [
                ("--report",),
                ("--undo-log", str(root / "log.json")),
                ("--review-plans",),
                ("--apply-organization-plan",),
                ("--confirm", "APPLY_ORGANIZATION_PLAN"),
            ]
            for args in cases:
                with self.subTest(args=args):
                    result = run_cli(root, "--html-report", *args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("--html-report cannot be combined", result.stderr)

            self.assertFalse((root / "Organized").exists())

    def test_cli_html_report_output_requires_html_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            result = run_cli(root, "--html-report-output", str(root / "out.html"))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--html-report-output requires --html-report", result.stderr)

    def test_cli_html_report_does_not_call_executor_apply_move_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)
            from organizer import cli as cli_module

            with mock.patch("sys.argv", ["organizer.cli", str(root), "--html-report"]):
                with mock.patch("sys.stdout"):
                    with mock.patch("organizer.cli.apply_move_plan") as mocked_apply:
                        exit_code = cli_module.main()

            self.assertEqual(exit_code, 0)
            mocked_apply.assert_not_called()
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())

    def test_existing_report_behavior_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_report_fixture(root)

            report_path = write_report(build_scan_report(root), root)

            self.assertEqual(report_path.suffix, ".json")
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["schema_version"], 1)


def sample_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": "2026-07-09T12:00:00+00:00",
        "scan_root": ".",
        "summary": {
            "file_count": 4,
            "total_bytes": 16,
            "duplicate_group_count": 1,
            "duplicate_candidate_count": 1,
            "review_candidate_count": 1,
            "review_candidate_counts_by_category": {"empty": 1},
            "project_group_count": 1,
            "organization_suggestion_count": 1,
            "refinement_status": "not_requested",
        },
        "duplicates": [
            {
                "sha256": "abc",
                "size_bytes": 4,
                "files": ["a.txt", "subdir/b.txt"],
            }
        ],
        "duplicate_review_plan": [
            {
                "source": "subdir/b.txt",
                "destination": "AI_Review/duplicates/subdir/b.txt",
                "reason": "exact duplicate of a.txt",
                "confidence": 100,
                "operation": "dry-run move",
                "overwrite_risk": False,
            }
        ],
        "review_candidates": [
            {
                "path": "empty_candidate.txt",
                "category": "empty",
                "reason": "file is 0 bytes and is not a known intentional placeholder",
                "confidence": 80,
            }
        ],
        "review_candidate_plan": [
            {
                "source": "empty_candidate.txt",
                "destination": "AI_Review/empty/empty_candidate.txt",
                "reason": "file is 0 bytes and is not a known intentional placeholder",
                "confidence": 80,
                "operation": "dry-run move",
                "overwrite_risk": False,
            }
        ],
        "project_groups": [
            {
                "group_name": "Evosim",
                "reason": "files share filename token evosim",
                "confidence": 70,
                "files": ["evosim_notes.txt", "evosim_report.pdf"],
            }
        ],
        "organization_suggestions": [
            {
                "group_name": "Evosim",
                "suggested_root": "Organized/Evosim",
                "plan_items": [
                    {
                        "source": "evosim_notes.txt",
                        "destination": "Organized/Evosim/notes/evosim_notes.txt",
                        "reason": "files share filename token evosim; suggested subfolder notes",
                        "confidence": 70,
                        "operation": "dry-run move",
                        "overwrite_risk": False,
                    }
                ],
            }
        ],
        "refined_organization_suggestions": [],
        "warnings": ["sample warning"],
    }


def create_report_fixture(root: Path) -> None:
    (root / "subdir").mkdir()
    (root / "a.txt").write_text("same", encoding="utf-8")
    (root / "subdir" / "b.txt").write_text("same", encoding="utf-8")
    (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
    (root / "evosim_report.pdf").write_text("report", encoding="utf-8")
    (root / "empty_candidate.txt").write_text("", encoding="utf-8")
    (root / "secret.txt").write_text("secret file body", encoding="utf-8")


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


def extract_path(output: str, prefix: str) -> Path:
    for line in output.splitlines():
        if line.startswith(prefix):
            return Path(line.removeprefix(prefix))
    raise AssertionError(f"path not found for prefix {prefix!r}")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
