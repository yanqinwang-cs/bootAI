from pathlib import Path
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from organizer.executor import apply_move_plan, undo_operation_log
from organizer.grouping import build_organization_suggestions, find_project_groups
from organizer.models import LLMRefinement, MovePlanItem, MoveResult, OperationLog
from organizer.scanner import scan_directory


class DeterministicOrganizationApplyTests(unittest.TestCase):
    def test_dry_run_organization_plan_remains_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)

            result = run_cli(root, "--plan-organization")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Dry-run organization plan", result.stdout)
            self.assertIn("Dry-run only", result.stdout)
            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertTrue((root / "evosim_report.pdf").exists())
            self.assertFalse((root / "Organized").exists())

    def test_apply_organization_plan_requires_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)

            result = run_cli(root, "--apply-organization-plan")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Apply refused", result.stdout)
            self.assertIn("APPLY_ORGANIZATION_PLAN", result.stdout)
            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertTrue((root / "evosim_report.pdf").exists())
            self.assertFalse((root / "Organized").exists())

    def test_confirmed_apply_moves_files_and_writes_operation_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)

            result = run_cli(
                root,
                "--apply-organization-plan",
                "--confirm",
                "APPLY_ORGANIZATION_PLAN",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Approved organization move", result.stdout)
            self.assertIn("Apply completed.", result.stdout)
            self.assertFalse((root / "evosim_notes.txt").exists())
            self.assertFalse((root / "evosim_report.pdf").exists())
            self.assertTrue(
                (root / "Organized" / "Evosim" / "notes" / "evosim_notes.txt").exists()
            )
            self.assertTrue(
                (root / "Organized" / "Evosim" / "other" / "evosim_report.pdf").exists()
            )
            log_path = extract_operation_log_path(result.stdout)
            self.assertTrue(log_path.exists())

    def test_undo_restores_moved_organization_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)

            apply_result = run_cli(
                root,
                "--apply-organization-plan",
                "--confirm",
                "APPLY_ORGANIZATION_PLAN",
            )
            self.assertEqual(apply_result.returncode, 0, apply_result.stderr)
            log_path = extract_operation_log_path(apply_result.stdout)

            undo_result = run_cli(root, "--undo-log", str(log_path))

            self.assertEqual(undo_result.returncode, 0, undo_result.stderr)
            self.assertIn("Undo operation results", undo_result.stdout)
            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertTrue((root / "evosim_report.pdf").exists())

    def test_overwrite_destination_is_rejected_by_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)
            destination = root / "Organized" / "Evosim" / "notes" / "evosim_notes.txt"
            destination.parent.mkdir(parents=True)
            destination.write_text("existing", encoding="utf-8")
            plan_items = organization_plan_items(root)

            with self.assertRaises(ValueError):
                apply_move_plan(plan_items, root)

            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertEqual(destination.read_text(encoding="utf-8"), "existing")

    def test_outside_root_destination_is_rejected_by_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            root.mkdir()
            create_evosim_files(root)
            plan_items = organization_plan_items(root)
            bad_item = plan_items[0]
            plan_items[0] = type(bad_item)(
                source=bad_item.source,
                destination=base / "outside" / bad_item.destination.name,
                reason=bad_item.reason,
                confidence=bad_item.confidence,
                operation=bad_item.operation,
                overwrite_risk=False,
            )

            with self.assertRaises(ValueError):
                apply_move_plan(plan_items, root)

            self.assertTrue((root / "evosim_notes.txt").exists())

    def test_direct_symlink_source_is_rejected_by_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "evosim_notes.txt"
            link = root / "evosim_report.pdf"
            target.write_text("notes", encoding="utf-8")
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError):
                self.skipTest("Symlinks are not supported on this OS or filesystem")
            plan_items = [
                MovePlanItem(
                    source=link,
                    destination=root / "Organized" / "Evosim" / "other" / link.name,
                    reason="files share filename token evosim; suggested subfolder other",
                    confidence=70,
                    operation="dry-run move",
                    overwrite_risk=False,
                )
            ]

            with self.assertRaises(ValueError):
                apply_move_plan(plan_items, root)

            self.assertTrue(link.exists())

    def test_unsafe_symlink_destination_parent_is_rejected_by_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            create_evosim_files(root)
            try:
                (root / "Organized").symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("Symlinks are not supported on this OS or filesystem")
            plan_items = organization_plan_items(root)

            with self.assertRaises(ValueError):
                apply_move_plan(plan_items, root)

            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertFalse(any(outside.rglob("*")))

    def test_destination_collisions_do_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a" / "evosim.txt"
            second = root / "b" / "evosim.txt"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("a", encoding="utf-8")
            second.write_text("b", encoding="utf-8")

            result = run_cli(
                root,
                "--apply-organization-plan",
                "--confirm",
                "APPLY_ORGANIZATION_PLAN",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            destination = root / "Organized" / "Evosim" / "notes"
            self.assertEqual((destination / "evosim.txt").read_text(encoding="utf-8"), "a")
            self.assertEqual((destination / "b_evosim.txt").read_text(encoding="utf-8"), "b")

    def test_ai_review_files_are_not_reorganized_accidentally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)
            review_file = root / "AI_Review" / "notes" / "evosim_hidden.txt"
            review_file.parent.mkdir(parents=True)
            review_file.write_text("already reviewed", encoding="utf-8")

            result = run_cli(
                root,
                "--apply-organization-plan",
                "--confirm",
                "APPLY_ORGANIZATION_PLAN",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(review_file.exists())
            self.assertFalse(
                (root / "Organized" / "Evosim" / "notes" / "evosim_hidden.txt").exists()
            )


class RefinedOrganizationApplyTests(unittest.TestCase):
    def test_apply_refined_organization_plan_requires_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)

            exit_code, output = run_cli_main_with_refinement(
                root,
                "--apply-refined-organization-plan",
                "--llm-provider",
                "ollama",
                "--llm-model",
                "local-model",
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("Apply refused", output)
            self.assertIn("APPLY_REFINED_ORGANIZATION_PLAN", output)
            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertFalse((root / "Organized").exists())

    def test_confirmed_refined_apply_uses_validated_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)

            exit_code, output = run_cli_main_with_refinement(
                root,
                "--apply-refined-organization-plan",
                "--llm-provider",
                "ollama",
                "--llm-model",
                "local-model",
                "--confirm",
                "APPLY_REFINED_ORGANIZATION_PLAN",
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("Approved refined organization move", output)
            self.assertTrue(
                (root / "Organized" / "EvoSim_Project" / "notes" / "evosim_notes.txt").exists()
            )
            self.assertTrue(
                (root / "Organized" / "EvoSim_Project" / "documents" / "evosim_report.pdf").exists()
            )
            self.assertTrue(extract_operation_log_path(output).exists())

    def test_invalid_refined_output_cannot_be_applied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)

            with self.assertRaises(SystemExit):
                run_cli_main_with_refinement(
                    root,
                    "--apply-refined-organization-plan",
                    "--llm-provider",
                    "ollama",
                    "--llm-model",
                    "local-model",
                    "--confirm",
                    "APPLY_REFINED_ORGANIZATION_PLAN",
                    refinement_error=ValueError("invalid refined output"),
                )

            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertFalse((root / "Organized").exists())

    def test_refined_apply_operation_log_supports_undo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)

            exit_code, output = run_cli_main_with_refinement(
                root,
                "--apply-refined-organization-plan",
                "--llm-provider",
                "ollama",
                "--llm-model",
                "local-model",
                "--confirm",
                "APPLY_REFINED_ORGANIZATION_PLAN",
            )
            self.assertEqual(exit_code, 0)
            log_path = extract_operation_log_path(output)

            undo_log = undo_operation_log(log_path, root)

            self.assertTrue(all(result.success for result in undo_log.operations))
            self.assertTrue((root / "evosim_notes.txt").exists())
            self.assertTrue((root / "evosim_report.pdf").exists())

    def test_refined_apply_passes_move_plan_items_to_executor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)
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

            exit_code, _output = run_cli_main_with_refinement(
                root,
                "--apply-refined-organization-plan",
                "--llm-provider",
                "ollama",
                "--llm-model",
                "local-model",
                "--confirm",
                "APPLY_REFINED_ORGANIZATION_PLAN",
                apply_side_effect=fake_apply,
            )

            self.assertEqual(exit_code, 0)
            self.assertGreater(len(captured_plan_items), 0)
            self.assertTrue(all(item.operation == "dry-run move" for item in captured_plan_items))

    def test_cli_reports_partial_apply_failures_and_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_evosim_files(root)

            def fake_apply(plan_items, apply_root):
                return OperationLog(
                    log_path=apply_root / "AI_Review" / "operation_logs" / "fake.json",
                    operations=[
                        MoveResult(
                            source=plan_items[0].source,
                            destination=plan_items[0].destination,
                            success=True,
                            message="moved",
                        ),
                        MoveResult(
                            source=plan_items[1].source,
                            destination=plan_items[1].destination,
                            success=False,
                            message="move failed: simulated failure",
                        ),
                    ],
                )

            exit_code, output = run_cli_main_with_refinement(
                root,
                "--apply-refined-organization-plan",
                "--llm-provider",
                "ollama",
                "--llm-model",
                "local-model",
                "--confirm",
                "APPLY_REFINED_ORGANIZATION_PLAN",
                apply_side_effect=fake_apply,
            )

            self.assertEqual(exit_code, 1)
            self.assertIn("Apply completed with failures.", output)
            self.assertNotIn("Apply completed.\n", output)


def create_evosim_files(root: Path) -> None:
    (root / "evosim_notes.txt").write_text("notes", encoding="utf-8")
    (root / "evosim_report.pdf").write_text("report", encoding="utf-8")


def organization_plan_items(root: Path):
    metadata_items = scan_directory(root)
    groups = find_project_groups(metadata_items)
    suggestions = build_organization_suggestions(groups, root)
    return [
        item
        for suggestion in suggestions
        for item in suggestion.plan_items
    ]


def valid_refinements(groups):
    refinements = []
    for group in groups:
        refinements.append(
            LLMRefinement(
                original_group_name=group.group_name,
                folder_name="EvoSim_Project",
                confidence=82,
                reason="suggested grouping based on provided paths",
                subfolders={
                    file.relative_path.as_posix(): (
                        "documents"
                        if file.extension == ".pdf"
                        else "notes"
                    )
                    for file in group.files
                },
                warnings=[],
            )
        )
    return refinements


def run_cli_main_with_refinement(
    root: Path,
    *args: str,
    refinement_error: Exception | None = None,
    apply_side_effect=None,
) -> tuple[int, str]:
    from organizer import cli as cli_module

    def fake_refine(groups, client):
        if refinement_error is not None:
            raise refinement_error
        return valid_refinements(groups)

    stdout = io.StringIO()
    stderr = io.StringIO()
    argv = ["organizer.cli", str(root), *args]
    apply_mock = mock.patch("organizer.cli.apply_move_plan", side_effect=apply_side_effect)
    if apply_side_effect is None:
        apply_mock = mock.patch("organizer.cli.apply_move_plan", wraps=apply_move_plan)

    with mock.patch("sys.argv", argv):
        with mock.patch("sys.stdout", stdout):
            with mock.patch("sys.stderr", stderr):
                with mock.patch("organizer.cli.refine_project_groups_with_ollama", side_effect=fake_refine):
                    with apply_mock:
                        exit_code = cli_module.main()
    return exit_code, stdout.getvalue()


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


def extract_operation_log_path(output: str) -> Path:
    for line in output.splitlines():
        if line.startswith("Operation log: "):
            return Path(line.removeprefix("Operation log: "))
    raise AssertionError("Operation log path not found in CLI output")


if __name__ == "__main__":
    unittest.main()
