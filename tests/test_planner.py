from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from organizer.duplicates import find_exact_duplicates
from organizer.models import DuplicateGroup, FileMetadata
from organizer.planner import build_duplicate_review_plan, choose_reference_file
from organizer.scanner import scan_directory


def make_metadata(path: str) -> FileMetadata:
    relative_path = Path(path)
    return FileMetadata(
        path=Path("/scan-root") / relative_path,
        relative_path=relative_path,
        name=relative_path.name,
        extension=relative_path.suffix,
        size_bytes=10,
        modified_time=0.0,
        is_dir=False,
    )


class PlannerTests(unittest.TestCase):
    def test_choose_reference_file_chooses_shortest_relative_path(self) -> None:
        short = make_metadata("a.txt")
        long = make_metadata("nested/a.txt")
        group = DuplicateGroup(sha256="hash", size_bytes=10, files=[long, short])

        self.assertEqual(choose_reference_file(group), short)

    def test_choose_reference_file_breaks_ties_alphabetically(self) -> None:
        first = make_metadata("a.txt")
        second = make_metadata("b.txt")
        group = DuplicateGroup(sha256="hash", size_bytes=10, files=[second, first])

        self.assertEqual(choose_reference_file(group), first)

    def test_build_duplicate_review_plan_keeps_reference_and_plans_rest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "copy.txt").write_text("same", encoding="utf-8")
            groups = find_exact_duplicates(scan_directory(root))

            plan = build_duplicate_review_plan(groups, root)

            self.assertEqual(len(plan), 1)
            self.assertEqual(plan[0].source, (nested / "copy.txt").resolve())
            self.assertEqual(
                plan[0].reason,
                "exact duplicate of a.txt",
            )

    def test_planned_destinations_are_under_review_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "copy.txt").write_text("same", encoding="utf-8")
            groups = find_exact_duplicates(scan_directory(root))

            plan = build_duplicate_review_plan(groups, root)

            self.assertEqual(
                plan[0].destination,
                root / "AI_Review" / "duplicates" / "nested" / "copy.txt",
            )

    def test_planned_destinations_preserve_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            nested = root / "nested" / "deeper"
            nested.mkdir(parents=True)
            (nested / "copy.txt").write_text("same", encoding="utf-8")
            groups = find_exact_duplicates(scan_directory(root))

            plan = build_duplicate_review_plan(groups, root)

            self.assertEqual(
                plan[0].destination.relative_to(root / "AI_Review" / "duplicates"),
                Path("nested/deeper/copy.txt"),
            )

    def test_overwrite_risk_false_when_destination_does_not_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            groups = find_exact_duplicates(scan_directory(root))

            plan = build_duplicate_review_plan(groups, root)

            self.assertFalse(plan[0].overwrite_risk)

    def test_overwrite_risk_true_when_destination_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            review_duplicate_path = root / "AI_Review" / "duplicates" / "b.txt"
            review_duplicate_path.parent.mkdir(parents=True)
            review_duplicate_path.write_text("existing", encoding="utf-8")
            groups = find_exact_duplicates(scan_directory(root))

            plan = build_duplicate_review_plan(groups, root)

            self.assertTrue(plan[0].overwrite_risk)

    def test_plan_operation_and_confidence_are_fixed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            groups = find_exact_duplicates(scan_directory(root))

            plan = build_duplicate_review_plan(groups, root)

            self.assertEqual(plan[0].operation, "dry-run move")
            self.assertEqual(plan[0].confidence, 100)

    def test_planner_does_not_create_directories_or_move_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            groups = find_exact_duplicates(scan_directory(root))

            build_duplicate_review_plan(groups, root)

            self.assertTrue((root / "a.txt").exists())
            self.assertTrue((root / "b.txt").exists())
            self.assertFalse((root / "AI_Review").exists())

    def test_cli_plan_duplicates_runs_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = "src"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "organizer.cli",
                    str(root),
                    "--plan-duplicates",
                ],
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Dry-run duplicate review plan", result.stdout)
            self.assertIn("Dry-run only", result.stdout)
            self.assertIn("Planned action 1:", result.stdout)
            self.assertNotIn("delete", result.stdout.lower())
            self.assertNotIn("safe to delete", result.stdout.lower())
            self.assertNotIn("cleanup automatically", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
