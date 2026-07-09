from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from organizer.review import build_review_candidate_plan, detect_review_candidates
from organizer.scanner import scan_directory

FORBIDDEN_OUTPUT_TERMS = [
    "delete",
    "safe to delete",
    "useless",
    "cleanup automatically",
    "permanent cleanup",
]


class ReviewDetectionTests(unittest.TestCase):
    def test_detects_empty_file_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "empty.txt").write_text("", encoding="utf-8")

            candidates = detect_review_candidates(scan_directory(root))

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].category, "empty")
            self.assertEqual(candidates[0].confidence, 80)

    def test_does_not_flag_known_intentional_empty_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["__init__.py", ".gitkeep", ".keep"]:
                (root / name).write_text("", encoding="utf-8")

            candidates = detect_review_candidates(scan_directory(root))

            self.assertEqual(candidates, [])

    def test_detects_temporary_system_artifact_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = [
                ".DS_Store",
                "Thumbs.db",
                "desktop.ini",
                "download.part",
                "chrome.crdownload",
                "swap.swp",
                "~draft.txt",
                ".~lock",
                "~$sheet.xlsx",
                "notes.txt~",
            ]
            for name in names:
                (root / name).write_text("temporary", encoding="utf-8")

            candidates = detect_review_candidates(scan_directory(root))

            self.assertEqual(len(candidates), len(names))
            self.assertEqual({candidate.category for candidate in candidates}, {"temporary"})
            self.assertTrue(all(candidate.confidence == 95 for candidate in candidates))

    def test_detects_backup_copy_marker_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = [
                "report copy.txt",
                "photo-backup.jpg",
                "notes_bak.md",
                "slides-old.pptx",
                "budget.previous.xlsx",
                "draft-prev.txt",
                "essay-finalfinal.docx",
                "data_duplicate.csv",
                "archive-duplicated.zip",
            ]
            for name in names:
                (root / name).write_text("marker", encoding="utf-8")

            candidates = detect_review_candidates(scan_directory(root))

            self.assertEqual(len(candidates), len(names))
            self.assertEqual({candidate.category for candidate in candidates}, {"backup_or_copy"})
            self.assertTrue(all(candidate.confidence == 70 for candidate in candidates))

    def test_does_not_match_backup_copy_tokens_inside_unrelated_words(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "copywriting_notes.txt").write_text("notes", encoding="utf-8")
            (root / "backupify.txt").write_text("notes", encoding="utf-8")

            candidates = detect_review_candidates(scan_directory(root))

            self.assertEqual(candidates, [])

    def test_ignores_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "folder.tmp").mkdir()

            candidates = detect_review_candidates(scan_directory(root))

            self.assertEqual(candidates, [])

    def test_ignores_files_already_under_review_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_file = root / "AI_Review" / "temporary" / "file.tmp"
            review_file.parent.mkdir(parents=True)
            review_file.write_text("temporary", encoding="utf-8")

            candidates = detect_review_candidates(scan_directory(root))

            self.assertEqual(candidates, [])

    def test_returns_candidates_sorted_by_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "z.tmp").write_text("temporary", encoding="utf-8")
            (root / "a.tmp").write_text("temporary", encoding="utf-8")

            candidates = detect_review_candidates(scan_directory(root))

            self.assertEqual(
                [candidate.file.relative_path.as_posix() for candidate in candidates],
                ["a.tmp", "z.tmp"],
            )

    def test_detects_isolated_orphan_code_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["practice.py", "Example.java", "analysis.ipynb"]:
                (root / name).write_text("code", encoding="utf-8")

            candidates = detect_review_candidates(scan_directory(root))

            self.assertEqual(
                {candidate.file.name for candidate in candidates},
                {"practice.py", "Example.java", "analysis.ipynb"},
            )
            self.assertEqual({candidate.category for candidate in candidates}, {"orphan_code"})

    def test_project_and_dependency_code_are_not_orphan_code_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            (project / "pyproject.toml").write_text("[project]", encoding="utf-8")
            (project / "app.py").write_text("print('x')", encoding="utf-8")
            node_file = root / "node_modules" / "pkg" / "index.js"
            node_file.parent.mkdir(parents=True)
            node_file.write_text("console.log('x')", encoding="utf-8")
            app_file = root / "Example.app" / "Contents" / "script.py"
            app_file.parent.mkdir(parents=True)
            app_file.write_text("print('x')", encoding="utf-8")

            candidates = detect_review_candidates(scan_directory(root))

            self.assertEqual(candidates, [])


class ReviewPlanTests(unittest.TestCase):
    def test_plan_destinations_are_under_review_category_and_preserve_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "subdir"
            nested.mkdir()
            (nested / "file.tmp").write_text("temporary", encoding="utf-8")
            candidates = detect_review_candidates(scan_directory(root))

            plan = build_review_candidate_plan(candidates, root)

            self.assertEqual(len(plan), 1)
            self.assertEqual(
                plan[0].destination,
                root / "AI_Review" / "temporary" / "subdir" / "file.tmp",
            )

    def test_orphan_code_plan_destination_uses_orphan_code_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "practice"
            nested.mkdir()
            (nested / "script.py").write_text("print('x')", encoding="utf-8")
            candidates = detect_review_candidates(scan_directory(root))

            plan = build_review_candidate_plan(candidates, root)

            self.assertEqual(len(plan), 1)
            self.assertEqual(
                plan[0].destination,
                root / "AI_Review" / "orphan_code" / "practice" / "script.py",
            )

    def test_plan_operation_reason_and_confidence_are_copied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file.tmp").write_text("temporary", encoding="utf-8")
            candidates = detect_review_candidates(scan_directory(root))

            plan = build_review_candidate_plan(candidates, root)

            self.assertEqual(plan[0].operation, "dry-run move")
            self.assertEqual(plan[0].reason, candidates[0].reason)
            self.assertEqual(plan[0].confidence, candidates[0].confidence)

    def test_plan_overwrite_risk_false_when_destination_does_not_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file.tmp").write_text("temporary", encoding="utf-8")
            candidates = detect_review_candidates(scan_directory(root))

            plan = build_review_candidate_plan(candidates, root)

            self.assertFalse(plan[0].overwrite_risk)

    def test_plan_overwrite_risk_true_when_destination_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file.tmp").write_text("temporary", encoding="utf-8")
            destination = root / "AI_Review" / "temporary" / "file.tmp"
            destination.parent.mkdir(parents=True)
            destination.write_text("existing", encoding="utf-8")
            candidates = detect_review_candidates(scan_directory(root))

            plan = build_review_candidate_plan(candidates, root)

            self.assertTrue(plan[0].overwrite_risk)

    def test_plan_does_not_create_directories_or_move_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "file.tmp"
            source.write_text("temporary", encoding="utf-8")
            candidates = detect_review_candidates(scan_directory(root))

            build_review_candidate_plan(candidates, root)

            self.assertTrue(source.exists())
            self.assertFalse((root / "AI_Review").exists())


class ReviewCliTests(unittest.TestCase):
    def test_cli_review_candidates_runs_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file.tmp").write_text("temporary", encoding="utf-8")

            result = run_cli(root, "--review-candidates")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Review candidates", result.stdout)
            self.assertIn("Candidate for review", result.stdout)
            assert_forbidden_terms_absent(self, result.stdout)

    def test_cli_plan_review_candidates_runs_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file.tmp").write_text("temporary", encoding="utf-8")

            result = run_cli(root, "--plan-review-candidates")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Dry-run review candidate plan", result.stdout)
            self.assertIn("Dry-run only", result.stdout)
            assert_forbidden_terms_absent(self, result.stdout)

    def test_cli_combined_review_flags_print_candidates_then_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file.tmp").write_text("temporary", encoding="utf-8")

            result = run_cli(root, "--review-candidates", "--plan-review-candidates")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(
                result.stdout.index("Review candidates"),
                result.stdout.index("Dry-run review candidate plan"),
            )
            assert_forbidden_terms_absent(self, result.stdout)


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


def assert_forbidden_terms_absent(test_case: unittest.TestCase, output: str) -> None:
    lowered = output.lower()
    for term in FORBIDDEN_OUTPUT_TERMS:
        test_case.assertNotIn(term, lowered)


if __name__ == "__main__":
    unittest.main()
