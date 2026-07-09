from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from organizer.grouping import (
    build_organization_suggestions,
    extract_course_code,
    extract_filename_tokens,
    find_project_groups,
    infer_subfolder,
)
from organizer.models import FileMetadata, ProjectGroup
from organizer.scanner import scan_directory

FORBIDDEN_OUTPUT_TERMS = [
    "delete",
    "safe to delete",
    "useless",
    "cleanup automatically",
    "permanent cleanup",
]


def metadata_for(relative_path: str) -> FileMetadata:
    path = Path("/tmp") / relative_path
    return FileMetadata(
        path=path,
        relative_path=Path(relative_path),
        name=path.name,
        extension=path.suffix,
        size_bytes=10,
        modified_time=0.0,
        is_dir=False,
    )


class GroupingTokenTests(unittest.TestCase):
    def test_extract_course_code_detects_common_codes(self) -> None:
        for code in ["CS2103", "CS2103T", "CS2030S", "MA2001", "ST2334", "IS1108"]:
            self.assertEqual(extract_course_code(metadata_for(f"{code}_notes.pdf")), code)

    def test_extract_course_code_returns_none_when_absent(self) -> None:
        self.assertIsNone(extract_course_code(metadata_for("project_notes.pdf")))

    def test_extract_filename_tokens_splits_and_removes_weak_tokens(self) -> None:
        tokens = extract_filename_tokens(
            metadata_for("EvoSim-final_copy-v2_analysis-notes.pdf")
        )

        self.assertEqual(tokens, {"evosim", "v2", "analysis", "notes"})

    def test_infer_subfolder_covers_expected_categories(self) -> None:
        cases = {
            "reading-paper.pdf": "papers",
            "meeting_notes.md": "notes",
            "main.py": "code",
            "data.csv": "datasets",
            "experiment_results.bin": "results",
            "lecture.pptx": "slides",
            "diagram.png": "images",
            "archive.zip": "archives",
            "proposal.docx": "documents",
            "misc.bin": "other",
        }

        for filename, expected in cases.items():
            self.assertEqual(infer_subfolder(metadata_for(filename)), expected)


class ProjectGroupingTests(unittest.TestCase):
    def test_document_extensions_are_eligible_for_organization_groups(self) -> None:
        extensions = [
            ".pdf",
            ".md",
            ".markdown",
            ".txt",
            ".rtf",
            ".doc",
            ".docx",
            ".ppt",
            ".pptx",
        ]
        for extension in extensions:
            with self.subTest(extension=extension):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    (root / f"evosim_one{extension}").write_text("one", encoding="utf-8")
                    (root / f"evosim_two{extension}").write_text("two", encoding="utf-8")

                    groups = find_project_groups(scan_directory(root))

                    self.assertEqual(len(groups), 1)
                    self.assertEqual(groups[0].group_name, "Evosim")

    def test_groups_files_sharing_course_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CS2103_notes.pdf").write_text("notes", encoding="utf-8")
            (root / "assignment_CS2103.txt").write_text("assignment", encoding="utf-8")

            groups = find_project_groups(scan_directory(root))

            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].group_name, "CS2103")
            self.assertEqual(groups[0].confidence, 90)

    def test_groups_files_sharing_strong_filename_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
            (root / "evosim_analysis.pdf").write_text("analysis", encoding="utf-8")

            groups = find_project_groups(scan_directory(root))

            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].group_name, "Evosim")
            self.assertEqual(groups[0].confidence, 70)

    def test_does_not_group_below_min_group_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")

            groups = find_project_groups(scan_directory(root), min_group_size=2)

            self.assertEqual(groups, [])

    def test_ignores_directories_files_under_review_and_review_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evosim_folder").mkdir()
            review_file = root / "AI_Review" / "notes" / "evosim_plan.txt"
            review_file.parent.mkdir(parents=True)
            review_file.write_text("reviewed", encoding="utf-8")
            (root / "evosim.tmp").write_text("temporary", encoding="utf-8")
            (root / "evosim_copy.txt").write_text("copy", encoding="utf-8")
            (root / "evosim_empty.txt").write_text("", encoding="utf-8")

            groups = find_project_groups(scan_directory(root))

            self.assertEqual(groups, [])

    def test_each_file_appears_in_at_most_one_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "alpha_beta_one.txt").write_text("one", encoding="utf-8")
            (root / "alpha_two.txt").write_text("two", encoding="utf-8")
            (root / "beta_three.txt").write_text("three", encoding="utf-8")

            groups = find_project_groups(scan_directory(root))
            all_files = [
                file.relative_path.as_posix()
                for group in groups
                for file in group.files
            ]

            self.assertEqual(len(all_files), len(set(all_files)))

    def test_course_code_grouping_takes_precedence_over_token_grouping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evosim_CS2103_notes.txt").write_text("notes", encoding="utf-8")
            (root / "evosim_CS2103_report.pdf").write_text("report", encoding="utf-8")
            (root / "evosim_other.txt").write_text("other", encoding="utf-8")

            groups = find_project_groups(scan_directory(root))

            self.assertEqual(groups[0].group_name, "CS2103")
            self.assertNotIn("evosim_CS2103_notes.txt", [
                file.relative_path.as_posix()
                for group in groups[1:]
                for file in group.files
            ])

    def test_group_order_and_file_order_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "zeta_two.txt").write_text("two", encoding="utf-8")
            (root / "zeta_one.txt").write_text("one", encoding="utf-8")
            (root / "CS2103_b.txt").write_text("b", encoding="utf-8")
            (root / "CS2103_a.txt").write_text("a", encoding="utf-8")

            groups = find_project_groups(scan_directory(root))

            self.assertEqual([group.group_name for group in groups], ["CS2103", "Zeta"])
            self.assertEqual(
                [file.relative_path.as_posix() for file in groups[0].files],
                ["CS2103_a.txt", "CS2103_b.txt"],
            )

    def test_standalone_html_is_eligible_but_web_project_html_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "article_evosim.html").write_text("<h1>one</h1>", encoding="utf-8")
            (root / "receipt_evosim.htm").write_text("<h1>two</h1>", encoding="utf-8")
            web = root / "web_project"
            web.mkdir()
            (web / "index.html").write_text("<html></html>", encoding="utf-8")
            (web / "style.css").write_text("body{}", encoding="utf-8")
            (web / "app.js").write_text("console.log('x')", encoding="utf-8")
            (web / "package.json").write_text("{}", encoding="utf-8")

            groups = find_project_groups(scan_directory(root))
            grouped_paths = {
                file.relative_path.as_posix()
                for group in groups
                for file in group.files
            }

            self.assertIn("article_evosim.html", grouped_paths)
            self.assertIn("receipt_evosim.htm", grouped_paths)
            self.assertNotIn("web_project/index.html", grouped_paths)

    def test_code_media_archive_config_and_protected_contexts_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            excluded_paths = [
                "evosim.py",
                "evosim.java",
                "evosim.ipynb",
                "evosim.png",
                "evosim.zip",
                "evosim.json",
                "node_modules/pkg/evosim.txt",
                "Project.app/Contents/Resources/evosim.txt",
                "Lib.framework/Resources/evosim.txt",
                ".git/evosim.txt",
                "Protected_Workspaces/evosim.txt",
            ]
            for relative_path in excluded_paths:
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("excluded", encoding="utf-8")

            groups = find_project_groups(scan_directory(root))

            self.assertEqual(groups, [])

    def test_project_marker_context_is_excluded_from_organization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            (project / "pyproject.toml").write_text("[project]", encoding="utf-8")
            (project / "evosim_notes.txt").write_text("notes", encoding="utf-8")
            (project / "evosim_report.pdf").write_text("report", encoding="utf-8")

            groups = find_project_groups(scan_directory(root))

            self.assertEqual(groups, [])


class OrganizationSuggestionTests(unittest.TestCase):
    def test_suggestions_create_destinations_under_organized_group_subfolder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file_path = root / "evosim_notes.txt"
            file_path.write_text("notes", encoding="utf-8")
            file = metadata_by_path(scan_directory(root))["evosim_notes.txt"]
            group = ProjectGroup(
                group_name="Evosim",
                files=[file],
                reason="files share filename token evosim",
                confidence=70,
            )

            suggestions = build_organization_suggestions([group], root)

            self.assertEqual(len(suggestions), 1)
            self.assertEqual(
                suggestions[0].plan_items[0].destination,
                root / "Organized" / "Evosim" / "notes" / "evosim_notes.txt",
            )

    def test_suggestion_plan_item_fields_are_dry_run_and_group_derived(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file_path = root / "evosim_notes.txt"
            file_path.write_text("notes", encoding="utf-8")
            file = metadata_by_path(scan_directory(root))["evosim_notes.txt"]
            group = ProjectGroup(
                group_name="Evosim",
                files=[file],
                reason="files share filename token evosim",
                confidence=70,
            )

            plan_item = build_organization_suggestions([group], root)[0].plan_items[0]

            self.assertEqual(plan_item.operation, "dry-run move")
            self.assertEqual(plan_item.confidence, 70)
            self.assertEqual(
                plan_item.reason,
                "files share filename token evosim; suggested subfolder notes",
            )

    def test_overwrite_risk_is_true_when_destination_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file_path = root / "evosim_notes.txt"
            file_path.write_text("notes", encoding="utf-8")
            destination = root / "Organized" / "Evosim" / "notes" / "evosim_notes.txt"
            destination.parent.mkdir(parents=True)
            destination.write_text("existing", encoding="utf-8")
            file = metadata_by_path(scan_directory(root))["evosim_notes.txt"]
            group = ProjectGroup(
                group_name="Evosim",
                files=[file],
                reason="files share filename token evosim",
                confidence=70,
            )

            plan_item = build_organization_suggestions([group], root)[0].plan_items[0]

            self.assertTrue(plan_item.overwrite_risk)

    def test_destination_collisions_are_avoided_with_parent_prefixes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a" / "evosim.txt"
            second = root / "b" / "evosim.txt"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("notes a", encoding="utf-8")
            second.write_text("notes b", encoding="utf-8")
            groups = find_project_groups(scan_directory(root))

            suggestions = build_organization_suggestions(groups, root)
            destinations = [
                item.destination.name for item in suggestions[0].plan_items
            ]

            self.assertEqual(destinations, ["evosim.txt", "b_evosim.txt"])

    def test_suggestion_builder_skips_out_of_scope_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evosim.py").write_text("print('not organized')", encoding="utf-8")
            file = metadata_by_path(scan_directory(root))["evosim.py"]
            group = ProjectGroup(
                group_name="Evosim",
                files=[file],
                reason="files share filename token evosim",
                confidence=70,
            )

            suggestions = build_organization_suggestions([group], root)

            self.assertEqual(suggestions, [])

    def test_suggestions_do_not_create_directories_or_move_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
            (root / "evosim_report.pdf").write_text("report", encoding="utf-8")
            groups = find_project_groups(scan_directory(root))

            build_organization_suggestions(groups, root)

            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertTrue((root / "evosim_report.pdf").exists())
            self.assertFalse((root / "Organized").exists())


class GroupingCliTests(unittest.TestCase):
    def test_cli_project_groups_runs_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
            (root / "evosim_report.pdf").write_text("report", encoding="utf-8")

            result = run_cli(root, "--project-groups")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Project group suggestions", result.stdout)
            self.assertIn("Suggested group", result.stdout)
            assert_forbidden_terms_absent(self, result.stdout)

    def test_cli_plan_organization_runs_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
            (root / "evosim_report.pdf").write_text("report", encoding="utf-8")

            result = run_cli(root, "--plan-organization")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Dry-run organization plan", result.stdout)
            self.assertIn("Dry-run only", result.stdout)
            assert_forbidden_terms_absent(self, result.stdout)

    def test_cli_existing_review_and_apply_duplicate_behaviors_still_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file.tmp").write_text("temporary", encoding="utf-8")
            review_result = run_cli(root, "--plan-review-candidates")
            self.assertEqual(review_result.returncode, 0, review_result.stderr)
            self.assertIn("Dry-run review candidate plan", review_result.stdout)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            apply_result = run_cli(
                root,
                "--apply-duplicate-plan",
                "--confirm",
                "APPLY_DUPLICATE_PLAN",
            )
            self.assertEqual(apply_result.returncode, 0, apply_result.stderr)
            self.assertIn("Apply completed.", apply_result.stdout)


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [sys.executable, "-m", "organizer.cli", str(root), *args],
        check=False,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
    )


def metadata_by_path(files: list[FileMetadata]) -> dict[str, FileMetadata]:
    return {file.relative_path.as_posix(): file for file in files}


def assert_forbidden_terms_absent(test_case: unittest.TestCase, output: str) -> None:
    lowered = output.lower()
    for term in FORBIDDEN_OUTPUT_TERMS:
        test_case.assertNotIn(term, lowered)


if __name__ == "__main__":
    unittest.main()
