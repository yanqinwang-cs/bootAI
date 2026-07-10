from __future__ import annotations

from pathlib import Path
import re
import tempfile

import httpx

from organizer.application.scan_service import scan_root
from organizer.web.app import create_app
from organizer.web.config import WebAppConfig
from organizer.web.scan_jobs import ScanJobController, ScanJobSnapshot


class WebReviewFixture:
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        (self.root / "alpha.txt").write_text("same", encoding="utf-8")
        (self.root / "beta.txt").write_text("same", encoding="utf-8")
        for index in range(1, 7):
            (self.root / f"backup copy {index}.txt").write_text(
                f"candidate {index}",
                encoding="utf-8",
            )
        self.result = scan_root(self.root)
        self.token = "w" * 32
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
            job_id="generation-one",
            result=self.result,
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
        launched = await client.get(f"/launch/{self.token}")
        if launched.status_code != 303:
            await client.aclose()
            raise AssertionError("test browser could not authenticate")
        return client

    async def csrf(self, client: httpx.AsyncClient, path: str = "/review") -> str:
        response = await client.get(path)
        match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        if match is None:
            raise AssertionError("CSRF token was not rendered")
        return match.group(1)

    @staticmethod
    def origin_headers(**extra: str) -> dict[str, str]:
        return {"Origin": "http://127.0.0.1", **extra}

    def artifact_paths(self) -> set[str]:
        return {
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file()
        }
