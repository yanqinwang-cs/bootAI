from __future__ import annotations

import asyncio
from pathlib import Path
import re
import tempfile
import unittest

import httpx

from organizer.application.view_models import ScanApplicationResult, ScanSummary
from organizer.web.app import create_app
from organizer.web.config import WebAppConfig
from organizer.web.scan_jobs import ScanJobController


class WebScanDashboardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.token = "t" * 32
        self.app = create_app(
            WebAppConfig(
                self.root,
                session_secret="s" * 32,
                launch_token=self.token,
                testing=True,
            )
        )

    async def asyncTearDown(self) -> None:
        self.directory.cleanup()

    async def test_scan_requires_csrf_and_same_origin(self) -> None:
        async with _client(self.app) as client:
            await client.get(f"/launch/{self.token}")
            page = await client.get("/")
            csrf = _csrf(page.text)
            missing_origin = await client.post("/scan", data={"csrf_token": csrf})
            wrong_origin = await client.post(
                "/scan",
                data={"csrf_token": csrf},
                headers={"Origin": "http://evil.example"},
            )

        self.assertEqual(missing_origin.status_code, 403)
        self.assertEqual(wrong_origin.status_code, 403)

    async def test_scan_accepts_htmx_and_renders_completed_summary(self) -> None:
        report_path = self.root / "AI_Review" / "reports" / "scan.json"
        result = ScanApplicationResult(
            root=self.root,
            report={"summary": {}, "warnings": []},
            summary=ScanSummary(3, 2048, 1, 1024, 2, 4),
            warnings=("one warning",),
        )
        self.app.state.scan_jobs = ScanJobController(
            self.root,
            scan=lambda _: result,
            write_report=lambda _: report_path,
        )

        async with _client(self.app) as client:
            await client.get(f"/launch/{self.token}")
            page = await client.get("/")
            csrf = _csrf(page.text)
            response = await client.post(
                "/scan",
                data={"csrf_token": csrf},
                headers={"Origin": "http://127.0.0.1", "HX-Request": "true"},
            )
            await asyncio.sleep(0.02)
            status = await client.get("/scan/status?surface=scans")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(status.status_code, 200)
        self.assertIn("Scan completed", status.text)
        self.assertIn("Space used by extra copies", status.text)
        self.assertIn("AI_Review/reports/scan.json", status.text)
        self.assertNotIn("Space saved", status.text)
        self.assertNotIn("Safe to delete", status.text)
        self.assertNotIn("hx-trigger", status.text)

    async def test_duplicate_scan_returns_conflict(self) -> None:
        self.app.state.scan_jobs = ScanJobController(
            self.root,
            scan=lambda path: ScanApplicationResult(
                root=path,
                report={"summary": {}, "warnings": []},
                summary=ScanSummary(0, 0, 0, 0, 0, 0),
                warnings=(),
            ),
            write_report=lambda _: self.root / "report.json",
        )

        async with _client(self.app) as client:
            await client.get(f"/launch/{self.token}")
            page = await client.get("/")
            self.app.state.scan_jobs._snapshot = self.app.state.scan_jobs._snapshot.__class__(
                status="scanning", job_id="active"
            )
            response = await client.post(
                "/scan",
                data={"csrf_token": _csrf(page.text)},
                headers={"Origin": "http://127.0.0.1"},
            )

        self.assertEqual(response.status_code, 409)


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if match is None:
        raise AssertionError("CSRF token not rendered")
    return match.group(1)


def _client(app: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://127.0.0.1",
        follow_redirects=True,
    )
