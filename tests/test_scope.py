from pathlib import Path
import tempfile
import unittest

from organizer.scanner import scan_directory
from organizer.scope import (
    is_actionable_plan_eligible,
    is_generated_asset_context_path,
    is_project_context_path,
    is_protected_context_path,
)


class ProtectedContextPathTests(unittest.TestCase):
    def test_protected_directory_paths_are_detected(self) -> None:
        protected_paths = [
            "node_modules/pkg/index.js",
            "repo/.git/config",
            ".venv/lib/site.py",
            "venv/lib/site.py",
            "pkg/__pycache__/module.pyc",
            "App.app/Contents/file.txt",
            "Lib.framework/Resources/file.txt",
            "Plugin.bundle/Contents/file.txt",
            "Project.xcodeproj/project.pbxproj",
            "Protected_Workspaces/project/file.txt",
        ]

        for relative_path in protected_paths:
            with self.subTest(relative_path=relative_path):
                self.assertTrue(is_protected_context_path(Path(relative_path)))

    def test_ordinary_document_path_is_not_protected(self) -> None:
        self.assertFalse(is_protected_context_path(Path("documents/report.pdf")))


class ProjectContextPathTests(unittest.TestCase):
    def test_project_marker_ancestor_is_project_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            (project / "pyproject.toml").write_text("[project]", encoding="utf-8")
            (project / "notes.txt").write_text("notes", encoding="utf-8")
            metadata = scan_directory(root)

            self.assertTrue(is_project_context_path(Path("project/notes.txt"), metadata))

    def test_actionable_plan_eligible_excludes_project_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            (project / "package.json").write_text("{}", encoding="utf-8")
            (project / "notes.txt").write_text("notes", encoding="utf-8")
            metadata = scan_directory(root)
            notes = [
                item for item in metadata if item.relative_path == Path("project/notes.txt")
            ][0]

            self.assertFalse(is_actionable_plan_eligible(notes, metadata))

    def test_actionable_plan_eligible_allows_ordinary_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("notes", encoding="utf-8")
            metadata = scan_directory(root)
            notes = [item for item in metadata if item.relative_path == Path("notes.txt")][0]

            self.assertTrue(is_actionable_plan_eligible(notes, metadata))


class GeneratedAndProjectOutputContextTests(unittest.TestCase):
    def test_generated_asset_folder_paths_are_detected(self) -> None:
        generated_paths = [
            "Instagram_files/example.js",
            "YouTube_files/base.js",
            "SomePage_files/style.css",
            "Any_files/image.webp",
            "Any_files/font.woff",
            "Any_files/icon.svg",
        ]

        for relative_path in generated_paths:
            with self.subTest(relative_path=relative_path):
                self.assertTrue(is_generated_asset_context_path(Path(relative_path)))

    def test_generated_and_project_output_files_are_not_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [
                "Instagram_files/example.js",
                "YouTube_files/base.js",
                "SomePage_files/style.css",
                "project/src/main.py",
                "project/resources/icon.png",
                "archive_experiment_files/output.txt",
                "experiment_outputs/result.txt",
            ]
            for relative_path in paths:
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x", encoding="utf-8")
            metadata = scan_directory(root)

            actionable_paths = {
                item.relative_path.as_posix()
                for item in metadata
                if is_actionable_plan_eligible(item, metadata)
            }

            for relative_path in paths:
                self.assertNotIn(relative_path, actionable_paths)

    def test_ordinary_resources_document_folder_is_still_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "course_resources" / "CS1010X notes.pdf"
            path.parent.mkdir()
            path.write_text("notes", encoding="utf-8")
            metadata = scan_directory(root)
            file = [
                item for item in metadata if item.relative_path == Path("course_resources/CS1010X notes.pdf")
            ][0]

            self.assertTrue(is_actionable_plan_eligible(file, metadata))

    def test_loose_python_file_is_not_generated_asset_context(self) -> None:
        self.assertFalse(is_generated_asset_context_path(Path("practice.py")))


if __name__ == "__main__":
    unittest.main()
