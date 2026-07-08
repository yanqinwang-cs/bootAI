from pathlib import Path
import tempfile
import unittest

from organizer.scanner import scan_directory


class ScanDirectoryTests(unittest.TestCase):
    def test_scans_files_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file_path = root / "notes.txt"
            file_path.write_text("hello", encoding="utf-8")

            results = scan_directory(root)
            metadata = {item.relative_path.as_posix(): item for item in results}

            self.assertIn(".", metadata)
            self.assertIn("notes.txt", metadata)
            self.assertEqual(metadata["notes.txt"].name, "notes.txt")
            self.assertEqual(metadata["notes.txt"].extension, ".txt")
            self.assertEqual(metadata["notes.txt"].size_bytes, 5)
            self.assertFalse(metadata["notes.txt"].is_dir)

    def test_records_relative_paths_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "docs" / "archive"
            nested.mkdir(parents=True)
            (nested / "report.md").write_text("report", encoding="utf-8")

            results = scan_directory(root)
            relative_paths = [item.relative_path for item in results]

            self.assertIn(Path("docs"), relative_paths)
            self.assertIn(Path("docs/archive"), relative_paths)
            self.assertIn(Path("docs/archive/report.md"), relative_paths)

    def test_respects_max_depth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "level1" / "level2"
            nested.mkdir(parents=True)
            (nested / "deep.txt").write_text("deep", encoding="utf-8")

            results = scan_directory(root, max_depth=1)
            relative_paths = {item.relative_path.as_posix() for item in results}

            self.assertIn(".", relative_paths)
            self.assertIn("level1", relative_paths)
            self.assertNotIn("level1/level2", relative_paths)
            self.assertNotIn("level1/level2/deep.txt", relative_paths)

    def test_handles_empty_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty_dir = root / "empty"
            empty_dir.mkdir()

            results = scan_directory(root)
            metadata = {item.relative_path.as_posix(): item for item in results}

            self.assertIn("empty", metadata)
            self.assertTrue(metadata["empty"].is_dir)

    def test_rejects_missing_or_file_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file_path = root / "file.txt"
            file_path.write_text("content", encoding="utf-8")

            with self.assertRaises(ValueError):
                scan_directory(root / "missing")
            with self.assertRaises(ValueError):
                scan_directory(file_path)

    def test_does_not_follow_unsafe_symlinks_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            outside = Path(directory) / "outside"
            root.mkdir()
            outside.mkdir()
            outside_file = outside / "secret.txt"
            outside_file.write_text("secret", encoding="utf-8")
            link = root / "outside-link"

            try:
                link.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("Symlinks are not supported on this OS or filesystem")

            results = scan_directory(root)
            relative_paths = {item.relative_path.as_posix() for item in results}

            self.assertNotIn("outside-link", relative_paths)
            self.assertNotIn("outside-link/secret.txt", relative_paths)


if __name__ == "__main__":
    unittest.main()
