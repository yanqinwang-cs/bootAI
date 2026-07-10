from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from organizer.web.config import WebAppConfig


class WebConfigTests(unittest.TestCase):
    def test_valid_root_is_resolved_and_configuration_is_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = WebAppConfig(root / ".")

            self.assertEqual(config.root, root.resolve())
            with self.assertRaises(FrozenInstanceError):
                config.root = root / "other"  # type: ignore[misc]

    def test_root_validation_reuses_shared_safety_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with mock.patch(
                "organizer.web.config.validate_under_root",
                wraps=__import__(
                    "organizer.web.config",
                    fromlist=["validate_under_root"],
                ).validate_under_root,
            ) as validator:
                config = WebAppConfig(root)

            self.assertEqual(config.root, root)
            validator.assert_called_once_with(root, root)

    def test_missing_and_non_directory_roots_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "does not exist"):
                WebAppConfig(root / "missing")

            file_path = root / "file.txt"
            file_path.write_text("content", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not a directory"):
                WebAppConfig(file_path)

    def test_secrets_are_random_and_independent_per_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = WebAppConfig(root)
            second = WebAppConfig(root)

            self.assertGreaterEqual(len(first.session_secret), 32)
            self.assertGreaterEqual(len(first.launch_token), 32)
            self.assertNotEqual(first.session_secret, second.session_secret)
            self.assertNotEqual(first.launch_token, second.launch_token)

    def test_weak_or_non_url_safe_secrets_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "session secret"):
                WebAppConfig(root, session_secret="short")
            with self.assertRaisesRegex(ValueError, "launch token"):
                WebAppConfig(root, launch_token="not/a/safe/token" * 3)

    def test_testserver_is_allowed_only_for_testing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            production = WebAppConfig(root)
            testing = WebAppConfig(root, testing=True)

            self.assertEqual(production.allowed_hosts, ("127.0.0.1", "localhost"))
            self.assertEqual(
                testing.allowed_hosts,
                ("127.0.0.1", "localhost", "testserver"),
            )


if __name__ == "__main__":
    unittest.main()
