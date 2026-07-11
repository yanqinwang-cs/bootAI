from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import httpx

from organizer.application.scan_service import scan_root
from organizer.web.app import create_app
from organizer.web.config import WebAppConfig
from organizer.web.scan_jobs import ScanJobController


class WebReviewRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        (self.root / "a.txt").write_text("same", encoding="utf-8")
        (self.root / "b.txt").write_text("same", encoding="utf-8")
        (self.root / "backup copy.txt").write_text("copy", encoding="utf-8")
        self.result = scan_root(self.root)
        token = "r" * 32
        self.app = create_app(
            WebAppConfig(
                self.root,
                session_secret="s" * 32,
                launch_token=token,
                testing=True,
            )
        )
        self.app.state.scan_jobs = ScanJobController(
            self.root,
            scan=lambda _: self.result,
            write_report=lambda _: self.root / "AI_Review" / "reports" / "scan.json",
        )
        self.app.state.scan_jobs._snapshot = self.app.state.scan_jobs._snapshot.__class__(
            status="completed",
            job_id="completed-generation",
            result=self.result,
        )
        self.token = token

    async def asyncTearDown(self) -> None:
        self.directory.cleanup()

    async def test_review_routes_render_rows_decisions_and_details_without_writes(self) -> None:
        before = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*"))
        async with _client(self.app) as client:
            await client.get(f"/launch/{self.token}")
            review = await client.get("/review/advanced")
            duplicate = await client.get("/review/advanced?category=duplicate")
            detail = await client.get("/review/items/D1")
            conflicts = await client.get("/review/conflicts")
            invalid = await client.get("/review/advanced?sort=not-a-field")
            post = await client.post("/review")
        after = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*"))

        self.assertEqual(review.status_code, 200)
        self.assertIn('<html lang="en">', review.text)
        self.assertIn("<title>Advanced review · bootAI</title>", review.text)
        self.assertIn('<main id="main-content"', review.text)
        self.assertIn('<caption>Review findings and decisions</caption>', review.text)
        self.assertIn('scope="col"', review.text)
        self.assertIn('for="decision-filter"', review.text)
        self.assertIn('aria-current="page"', review.text)
        self.assertIn('aria-label="Review results pages"', review.text)
        self.assertNotIn("onclick=", review.text)
        self.assertNotIn("<script>", review.text)
        self.assertIn("Exact duplicates", review.text)
        self.assertIn("D1", review.text)
        self.assertIn("Review later", review.text)
        self.assertIn("Organize current page", review.text)
        self.assertIn("Keep current page here", review.text)
        self.assertIn("Mark current page for later review", review.text)
        self.assertIn('aria-pressed="true"', review.text)
        self.assertIn("Save reviewed plan", review.text)
        self.assertIn("backup copy.txt", review.text)
        self.assertEqual(duplicate.status_code, 200)
        self.assertIn("1 matching rows", duplicate.text)
        self.assertEqual(detail.status_code, 200)
        self.assertIn("Current path", detail.text)
        self.assertIn("Suggested destination", detail.text)
        self.assertNotIn("<pre", detail.text)
        self.assertEqual(conflicts.status_code, 200)
        self.assertIn("Approved conflicts: 0", conflicts.text)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(post.status_code, 405)
        self.assertEqual(before, after)

    async def test_review_requires_authentication_and_rejects_unknown_ids(self) -> None:
        async with _client(self.app) as client:
            unauthenticated = await client.get("/review/advanced")
            await client.get(f"/launch/{self.token}")
            unknown = await client.get("/review/items=/tmp/secret")

        self.assertEqual(unauthenticated.status_code, 403)
        self.assertEqual(unknown.status_code, 404)


def _client(app: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://127.0.0.1",
        follow_redirects=True,
    )
