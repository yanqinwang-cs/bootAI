from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPOSITORY_ROOT / "src" / "organizer" / "web"


class WebDependencyHygieneTests(unittest.TestCase):
    def test_optional_dependencies_are_exact_and_core_remains_empty(self) -> None:
        data = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        project = data["project"]

        self.assertEqual(project["dependencies"], [])
        self.assertEqual(
            project["optional-dependencies"]["web"],
            [
                "fastapi==0.139.0",
                "starlette==1.3.1",
                "uvicorn==0.50.2",
                "jinja2==3.1.6",
                "itsdangerous==2.2.0",
            ],
        )
        self.assertEqual(
            project["optional-dependencies"]["web-test"],
            ["httpx==0.28.1"],
        )

        all_requirements = "\n".join(
            requirement.lower()
            for requirements in project["optional-dependencies"].values()
            for requirement in requirements
        )
        for forbidden in (
            "python-multipart",
            "openai",
            "python-dotenv",
            "sqlalchemy",
            "fastapi[",
        ):
            self.assertNotIn(forbidden, all_requirements)

    def test_lockfile_contains_the_exact_web_versions(self) -> None:
        lock = (REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8")
        for name, version in {
            "fastapi": "0.139.0",
            "starlette": "1.3.1",
            "uvicorn": "0.50.2",
            "jinja2": "3.1.6",
            "itsdangerous": "2.2.0",
            "httpx": "0.28.1",
        }.items():
            self.assertIn(f'name = "{name}"\nversion = "{version}"', lock)

    def test_package_data_covers_all_web_resources(self) -> None:
        data = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        patterns = set(data["tool"]["setuptools"]["package-data"]["organizer.web"])
        self.assertEqual(
            patterns,
            {
                "templates/*.html",
                "static/THIRD_PARTY_NOTICES.txt",
                "static/css/*.css",
                "static/js/*.js",
                "static/vendor/*.css",
                "static/vendor/*.js",
            },
        )

    def test_vendor_assets_match_published_sha384_values(self) -> None:
        expected = {
            "htmx.min.js": (
                "H5SrcfygHmAuTDZphMHqBJLc3FhssKjG7w/"
                "CeCpFReSfwBWDTKpkzPP8c+cLsK+V"
            ),
            "bootstrap.min.css": (
                "sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWL"
                "zeN8tE5YBujZqJLB"
            ),
            "bootstrap.bundle.min.js": (
                "FKyoEForCGlyvwx9Hj09JcYn3nv7wiPVlz7YYwJrWVcXK/"
                "BmnVDxM+D2scQbITxI"
            ),
        }
        vendor = WEB_ROOT / "static" / "vendor"
        for filename, digest in expected.items():
            with self.subTest(filename=filename):
                actual = base64.b64encode(
                    hashlib.sha384((vendor / filename).read_bytes()).digest()
                ).decode("ascii")
                self.assertEqual(actual, digest)
        self.assertFalse(any(WEB_ROOT.rglob("*.map")))

    def test_runtime_pages_have_no_external_asset_or_inline_script_reference(self) -> None:
        authored_assets = [
            *sorted((WEB_ROOT / "templates").glob("*.html")),
            WEB_ROOT / "static" / "css" / "bootai.css",
            WEB_ROOT / "static" / "js" / "bootai.js",
        ]
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in authored_assets
        ).lower()
        for forbidden in (
            "http://",
            "https://",
            "cdn",
            "@import",
            "<script>",
            "onclick=",
            "onload=",
            "telemetry",
            "analytics",
        ):
            self.assertNotIn(forbidden, combined)

    def test_web_routes_use_application_services_not_domain_owners(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((WEB_ROOT / "routes").rglob("*.py"))
        ).lower()
        all_web_code = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(WEB_ROOT.rglob("*.py"))
        ).lower()
        for forbidden in (
            "organizer.executor",
            "organizer.scanner",
            "organizer.duplicates",
            "organizer.planner",
            "from organizer.review import",
            "from organizer.review_session import",
            "from organizer.review_state import",
            "import organizer.review",
            "import organizer.review_session",
            "import organizer.review_state",
            "organizer.grouping",
            "organizer.reports",
        ):
            self.assertNotIn(forbidden, combined)
        for forbidden in ("organizer.executor", "restore", "sqlite"):
            self.assertNotIn(forbidden, all_web_code)
        self.assertIn("organizer.application.scan_service", all_web_code)
        self.assertIn("organizer.application.review_service", combined)
        self.assertNotIn(
            "from organizer.application.review_service import create_review_session\n",
            combined,
        )
        self.assertIn(
            "from organizer.safety import validate_under_root",
            all_web_code,
        )

    def test_core_and_web_config_import_without_optional_dependencies(self) -> None:
        command = [
            sys.executable,
            "-S",
            "-c",
            "import organizer; import organizer.web; from organizer.web import WebAppConfig",
        ]
        environment = {"PYTHONPATH": str(REPOSITORY_ROOT / "src")}
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_launcher_reports_a_concise_missing_extra_error(self) -> None:
        result = subprocess.run(
            [sys.executable, "-S", "-m", "organizer.web", "--help"],
            cwd=REPOSITORY_ROOT,
            env={"PYTHONPATH": str(REPOSITORY_ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("bootai[web]", result.stderr)
        self.assertNotIn("traceback", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
