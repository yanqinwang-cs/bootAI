from __future__ import annotations

import unittest

from tests.web_consumer_support import ConsumerWebFixture


class LeaveWarningTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_internal_navigation_has_no_global_leave_warning(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            await client.post(
                "/review/items/D1/decision?surface=duplicates",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            pages = [
                await client.get(path)
                for path in (
                    "/",
                    "/duplicates",
                    "/organize",
                    "/attention",
                    "/scans",
                    "/settings",
                    "/review/advanced",
                    "/review/items/D1",
                    "/review/conflicts",
                )
            ]
            script = await client.get("/static/js/bootai.js")
        finally:
            await client.aclose()

        self.assertTrue(all(response.status_code == 200 for response in pages))
        self.assertEqual(self.decision("D1"), "rejected")
        self.assertTrue(self.session().dirty)
        self.assertNotIn("beforeunload", script.text)
        self.assertNotIn("onbeforeunload", "".join(page.text for page in pages))
        self.assertIn("htmx:afterSwap", script.text)

    async def test_server_still_blocks_scan_while_dirty_and_save_is_explicit(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            await client.post(
                "/review/items/D1/decision?surface=duplicates",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            blocked = await client.post(
                "/scan?surface=scans",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            saved = await client.post(
                "/review/save?surface=duplicates&page=1",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            saved_page = await client.get(saved.headers["location"])
        finally:
            await client.aclose()

        self.assertEqual(blocked.status_code, 409)
        self.assertIn("did not discard", blocked.text)
        self.assertEqual(saved.status_code, 303)
        self.assertIn("Choices saved", saved_page.text)
        self.assertIn("No files have moved", saved_page.text)
        self.assertFalse(self.session().dirty)


if __name__ == "__main__":
    unittest.main()
