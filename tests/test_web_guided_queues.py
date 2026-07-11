from __future__ import annotations

import unittest

from organizer.application.view_models import ReviewModule
from tests.web_consumer_support import ConsumerWebFixture


class WebGuidedQueueTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_skip_is_deferred_and_revisit_restores_queue_without_dirtying(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            skipped = await client.post(
                "/review/items/D1/decision?surface=duplicates",
                data={"csrf_token": csrf, "decision": "undecided"},
                headers=self.origin_headers(),
            )
            skipped_page = await client.get(skipped.headers["location"])
            revisited = await client.post(
                "/duplicates/revisit-skipped",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            revisited_page = await client.get(revisited.headers["location"])
        finally:
            await client.aclose()
        self.assertIn("1 skipped for now", skipped_page.text)
        self.assertIn("Review skipped files", skipped_page.text)
        self.assertIn("Skipped files returned", revisited_page.text)
        self.assertIn("beta backup copy.txt", revisited_page.text)
        self.assertFalse(self.session().dirty)

    async def test_new_generation_invalidates_queue_state(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            await client.post(
                "/review/items/D1/decision?surface=duplicates",
                data={"csrf_token": csrf, "decision": "undecided"},
                headers=self.origin_headers(),
            )
            self.controller._snapshot = self.controller.snapshot().__class__(
                status="completed",
                job_id="consumer-generation-two",
                result=self.result,
                report_path=self.root / "AI_Review" / "reports" / "scan-two.json",
            )
            page = await client.get("/duplicates")
        finally:
            await client.aclose()
        self.assertIn("0 of 1 reviewed", page.text)
        queue = self.app.state.review_explorer.snapshot(
            self.app.state.scan_jobs.snapshot()
        ).queue_for(ReviewModule.DUPLICATES)
        self.assertEqual(queue.deferred_ids, ())

    async def test_guided_markup_is_accessible_and_uses_no_inline_behavior(self) -> None:
        client = await self.authenticated_client()
        try:
            page = await client.get("/duplicates")
            css = await client.get("/static/css/bootai.css")
        finally:
            await client.aclose()
        self.assertEqual(page.text.count("<h1"), 1)
        self.assertIn("<progress", page.text)
        self.assertIn('aria-label="0 of 1 findings reviewed"', page.text)
        self.assertIn("Choose for beta backup copy.txt", page.text)
        self.assertNotIn("onclick=", page.text)
        self.assertNotIn("<script>", page.text)
        self.assertIn("prefers-reduced-motion", css.text)


if __name__ == "__main__":
    unittest.main()
