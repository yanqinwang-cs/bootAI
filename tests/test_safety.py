from pathlib import Path
import tempfile
import unittest

from organizer.safety import validate_under_root


class SafetyTests(unittest.TestCase):
    def test_validate_under_root_accepts_root_child(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child.txt"
            child.write_text("content", encoding="utf-8")

            self.assertEqual(validate_under_root(child, root), child.resolve())

    def test_validate_under_root_rejects_paths_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            outside = base / "outside.txt"
            root.mkdir()
            outside.write_text("content", encoding="utf-8")

            with self.assertRaises(ValueError):
                validate_under_root(outside, root)


if __name__ == "__main__":
    unittest.main()
