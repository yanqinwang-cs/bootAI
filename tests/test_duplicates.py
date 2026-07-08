from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from organizer.duplicates import find_exact_duplicates, hash_file
from organizer.scanner import scan_directory


class DuplicateTests(unittest.TestCase):
    def test_hash_file_returns_same_hash_for_identical_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("same content", encoding="utf-8")
            second.write_text("same content", encoding="utf-8")

            self.assertEqual(hash_file(first), hash_file(second))

    def test_hash_file_returns_different_hashes_for_different_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first content", encoding="utf-8")
            second.write_text("second content", encoding="utf-8")

            self.assertNotEqual(hash_file(first), hash_file(second))

    def test_hash_file_reads_in_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunked.bin"
            path.write_bytes(b"abcdef")

            self.assertEqual(hash_file(path), hash_file(path, chunk_size=2))

    def test_hash_file_rejects_directories_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.txt"
            link = root / "link.txt"
            target.write_text("content", encoding="utf-8")

            with self.assertRaises(ValueError):
                hash_file(root)

            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError):
                self.skipTest("Symlinks are not supported on this OS or filesystem")

            with self.assertRaises(ValueError):
                hash_file(link)

    def test_find_exact_duplicates_finds_duplicate_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.txt").write_text("duplicate", encoding="utf-8")
            (root / "second.txt").write_text("duplicate", encoding="utf-8")

            groups = find_exact_duplicates(scan_directory(root))

            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].size_bytes, len("duplicate"))
            self.assertEqual(
                [file.relative_path.as_posix() for file in groups[0].files],
                ["first.txt", "second.txt"],
            )

    def test_find_exact_duplicates_ignores_unique_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.txt").write_text("first", encoding="utf-8")
            (root / "second.txt").write_text("second", encoding="utf-8")

            self.assertEqual(find_exact_duplicates(scan_directory(root)), [])

    def test_find_exact_duplicates_ignores_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "empty-a").mkdir()
            (root / "empty-b").mkdir()

            self.assertEqual(find_exact_duplicates(scan_directory(root)), [])

    def test_duplicate_groups_are_sorted_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small-b.txt").write_text("aa", encoding="utf-8")
            (root / "small-a.txt").write_text("aa", encoding="utf-8")
            (root / "large-b.txt").write_text("bbbb", encoding="utf-8")
            (root / "large-a.txt").write_text("bbbb", encoding="utf-8")

            groups = find_exact_duplicates(scan_directory(root))

            self.assertEqual([group.size_bytes for group in groups], [4, 2])
            self.assertEqual(
                [file.relative_path.as_posix() for file in groups[0].files],
                ["large-a.txt", "large-b.txt"],
            )
            self.assertEqual(
                [file.relative_path.as_posix() for file in groups[1].files],
                ["small-a.txt", "small-b.txt"],
            )

    def test_same_size_duplicate_groups_sort_by_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a1.txt").write_text("aa", encoding="utf-8")
            (root / "a2.txt").write_text("aa", encoding="utf-8")
            (root / "b1.txt").write_text("bb", encoding="utf-8")
            (root / "b2.txt").write_text("bb", encoding="utf-8")

            groups = find_exact_duplicates(scan_directory(root))

            self.assertEqual(
                [group.sha256 for group in groups],
                sorted(group.sha256 for group in groups),
            )

    def test_cli_duplicate_mode_runs_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.txt").write_text("duplicate", encoding="utf-8")
            (root / "second.txt").write_text("duplicate", encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = "src"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "organizer.cli",
                    str(root),
                    "--duplicates",
                ],
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Metadata report", result.stdout)
            self.assertIn("Exact duplicate groups", result.stdout)
            self.assertIn("Group 1:", result.stdout)
            self.assertNotIn("safe to delete", result.stdout.lower())
            self.assertNotIn("delete", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
