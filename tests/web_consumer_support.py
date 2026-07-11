from __future__ import annotations

from pathlib import Path
import re
import tempfile

import httpx

from organizer.application.scan_service import scan_root
from organizer.web.app import create_app
from organizer.web.config import WebAppConfig
from organizer.web.scan_jobs import ScanJobController, ScanJobSnapshot


class ConsumerWebFixture:
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        (self.root / "alpha.txt").write_text("same", encoding="utf-8")
        (self.root / "beta backup copy.txt").write_text("same", encoding="utf-8")
        (self.root / "EvoSim_project_slides.pptx").write_text(
            "notes",
            encoding="utf-8",
        )
        (self.root / "EvoSim_project_slides_final.pptx").write_text(
            "report",
            encoding="utf-8",
        )
        (self.root / "empty.txt").write_text("", encoding="utf-8")
        self.result = scan_root(self.root)
        self.token = "c" * 32
        self.app = create_app(
            WebAppConfig(
                self.root,
                session_secret="s" * 32,
                launch_token=self.token,
                testing=True,
            )
        )
        self.controller = ScanJobController(
            self.root,
            scan=lambda _: self.result,
            write_report=lambda _: (
                self.root / "AI_Review" / "reports" / "scan.json"
            ),
        )
        self.controller._snapshot = ScanJobSnapshot(
            status="completed",
            job_id="consumer-generation",
            result=self.result,
            report_path=self.root / "AI_Review" / "reports" / "scan.json",
        )
        self.app.state.scan_jobs = self.controller

    def tearDown(self) -> None:
        self.directory.cleanup()

    async def authenticated_client(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://127.0.0.1",
            follow_redirects=False,
        )
        response = await client.get(f"/launch/{self.token}")
        if response.status_code != 303:
            await client.aclose()
            raise AssertionError("consumer browser could not authenticate")
        return client

    async def csrf(self, client: httpx.AsyncClient, path: str) -> str:
        response = await client.get(path)
        match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        if match is None:
            raise AssertionError("CSRF token was not rendered")
        return match.group(1)

    @staticmethod
    def origin_headers(**extra: str) -> dict[str, str]:
        return {"Origin": "http://127.0.0.1", **extra}

    def session(self):
        snapshot = self.app.state.review_explorer.snapshot(
            self.app.state.scan_jobs.snapshot()
        )
        if snapshot.session is None:
            raise AssertionError("consumer review session unavailable")
        return snapshot.session

    def decision(self, item_id: str) -> str:
        return next(item.decision for item in self.session().items if item.id == item_id)

    def file_snapshot(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.iterdir()
            if path.is_file()
        }
