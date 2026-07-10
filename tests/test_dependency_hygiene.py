from pathlib import Path
import subprocess
import tomllib
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class DependencyHygieneTests(unittest.TestCase):
    def test_core_metadata_has_no_mandatory_cloud_dependencies(self) -> None:
        data = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        project = data["project"]
        dependencies = [dependency.lower() for dependency in project["dependencies"]]

        self.assertEqual(project["name"], "bootai")
        self.assertNotEqual(project["description"], "Add your description here")
        self.assertEqual(project["requires-python"], ">=3.13")
        self.assertFalse(any("openai" in dependency for dependency in dependencies))
        self.assertFalse(any("python-dotenv" in dependency for dependency in dependencies))
        self.assertEqual(
            set(project["optional-dependencies"]),
            {"web", "web-test"},
        )
        self.assertEqual(data["tool"]["setuptools"]["package-dir"], {"": "src"})
        self.assertEqual(data["tool"]["setuptools"]["packages"]["find"]["where"], ["src"])

    def test_lockfile_has_no_cloud_dependencies(self) -> None:
        lock = (REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8").lower()
        self.assertNotIn('name = "openai"', lock)
        self.assertNotIn('name = "python-dotenv"', lock)
        self.assertIn('name = "bootai"', lock)

    def test_legacy_assistant_is_archived_outside_packaged_source(self) -> None:
        legacy = REPOSITORY_ROOT / "legacy" / "openrouter_code_assistant"
        self.assertTrue((legacy / "main.py").is_file())
        self.assertTrue((legacy / "call_function.py").is_file())
        self.assertTrue((legacy / "functions").is_dir())
        self.assertTrue((legacy / "calculator").is_dir())
        self.assertTrue((legacy / "README.md").is_file())
        self.assertFalse((REPOSITORY_ROOT / "main.py").exists())
        self.assertIn("openrouter", (legacy / "main.py").read_text(encoding="utf-8").lower())

    def test_organizer_source_has_no_cloud_runtime_imports(self) -> None:
        source_root = REPOSITORY_ROOT / "src" / "organizer"
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(source_root.rglob("*.py"))
        ).lower()
        for forbidden in (
            "from openai",
            "import openai",
            "openrouter",
            "openrouter_api_key",
            "load_dotenv",
        ):
            self.assertNotIn(forbidden, combined)

        non_web_combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(source_root.rglob("*.py"))
            if "web" not in path.relative_to(source_root).parts
        ).lower()
        for web_import in (
            "from fastapi",
            "import fastapi",
            "import uvicorn",
            "from starlette",
            "from jinja2",
        ):
            self.assertNotIn(web_import, non_web_combined)

        self.assertTrue((source_root / "web").is_dir())
        self.assertFalse((source_root / "application" / "preflight_service.py").exists())
        self.assertFalse((source_root / "application" / "execution_service.py").exists())

    def test_no_secret_or_environment_file_is_tracked(self) -> None:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        tracked = set(result.stdout.splitlines())
        self.assertNotIn(".env", tracked)
        self.assertFalse(any(path.endswith(".pem") for path in tracked))


if __name__ == "__main__":
    unittest.main()
