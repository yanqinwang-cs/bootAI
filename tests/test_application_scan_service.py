import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from organizer.application.scan_service import scan_root, write_scan_report
from organizer.ollama_client import OllamaClient
from organizer.reports import build_scan_report


class ScanServiceTests(unittest.TestCase):
    def test_write_scan_report_uses_collision_safe_report_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = scan_root(root)
            report_path = write_scan_report(result)

            self.assertEqual(report_path.name, next(report_path.parent.glob("*_report.json")).name)
            self.assertTrue(report_path.is_file())
            self.assertFalse((root / "operation_logs").exists())
    def test_deterministic_scan_returns_authoritative_report_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            (root / "backup copy.txt").write_text("different", encoding="utf-8")

            result = scan_root(root)

            self.assertEqual(result.root, root.resolve())
            self.assertEqual(result.summary.file_count, result.report["summary"]["file_count"])
            self.assertEqual(result.summary.total_bytes, result.report["summary"]["total_bytes"])
            self.assertEqual(result.summary.duplicate_group_count, 1)
            self.assertEqual(result.summary.potential_duplicate_bytes, 4)
            self.assertEqual(
                result.summary.review_candidate_count,
                result.report["summary"]["review_candidate_count"],
            )
            self.assertEqual(
                result.summary.organization_suggestion_count,
                result.report["summary"]["organization_suggestion_count"],
            )
            self.assertEqual(result.warnings, tuple(result.report["warnings"]))
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())

    def test_service_wraps_existing_report_object_without_a_second_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = build_scan_report(root)
            with mock.patch(
                "organizer.application.scan_service.build_scan_report",
                return_value=report,
            ) as builder:
                result = scan_root(root, max_depth=2)

            self.assertIs(result.report, report)
            builder.assert_called_once_with(
                root,
                max_depth=2,
                refine_groups=False,
                llm_client=None,
            )

    def test_empty_folder_and_rule_warnings_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty_result = scan_root(root)
            self.assertEqual(empty_result.summary.file_count, 0)
            self.assertEqual(empty_result.summary.potential_duplicate_bytes, 0)

            rules = root / "AI_Review" / "config" / "organization_rules.json"
            rules.parent.mkdir(parents=True)
            rules.write_text("{not json", encoding="utf-8")
            warning_result = scan_root(root)
            self.assertTrue(warning_result.warnings)
            self.assertEqual(warning_result.warnings, tuple(warning_result.report["warnings"]))

    def test_invalid_root_errors_are_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "does not exist"):
                scan_root(root / "missing")
            file_path = root / "file.txt"
            file_path.write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not a directory"):
                scan_root(file_path)

    def test_default_scan_does_not_prompt_print_or_require_llm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch(
                "builtins.input",
                side_effect=AssertionError("scan service must not prompt"),
            ), mock.patch(
                "organizer.reports.refine_project_groups_with_ollama"
            ) as refine, mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                scan_root(root)

            refine.assert_not_called()
            self.assertEqual(stdout.getvalue(), "")

    def test_explicit_ollama_client_is_forwarded_to_existing_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = build_scan_report(root)
            client = mock.create_autospec(OllamaClient, instance=True)
            with mock.patch(
                "organizer.application.scan_service.build_scan_report",
                return_value=report,
            ) as builder:
                scan_root(root, refine_groups=True, llm_client=client)

            builder.assert_called_once_with(
                root,
                max_depth=None,
                refine_groups=True,
                llm_client=client,
            )


if __name__ == "__main__":
    unittest.main()
