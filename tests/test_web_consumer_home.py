from __future__ import annotations

import unittest

from organizer.web.scan_jobs import ScanJobSnapshot
from tests.web_consumer_support import ConsumerWebFixture


class ConsumerHomeTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_initial_home_is_minimal_and_scan_is_explicit(self) -> None:
        self.controller._snapshot = ScanJobSnapshot(status="not_started")
        client = await self.authenticated_client()
        try:
            response = await client.get("/")
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text.count("<h1"), 1)
        self.assertIn("<h1 id=\"home-heading\">bootAI</h1>", response.text)
        self.assertIn("Selected folder", response.text)
        self.assertIn(self.root.name, response.text)
        self.assertNotIn(str(self.root), response.text)
        self.assertIn("Scan now", response.text)
        self.assertIn("Not configured", response.text)
        self.assertNotIn("review-table", response.text)
        self.assertNotIn("Stable ID", response.text)

    async def test_completed_home_uses_consolidated_consumer_counts(self) -> None:
        client = await self.authenticated_client()
        try:
            response = await client.get("/")
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Duplicate copies", response.text)
        self.assertIn("Space used by extra copies: 4 B", response.text)
        self.assertIn("Files ready to organize", response.text)
        self.assertIn("Needs attention", response.text)
        self.assertIn("Duplicates, organization, and attention choices", response.text)
        self.assertIn("AI_Review/reports/scan.json", response.text)
        self.assertIn("<summary>Technical details</summary>", response.text)
        self.assertNotIn("Potential reclaimable", response.text)
        self.assertNotIn("Storage recovered", response.text)
        self.assertNotIn("review-table", response.text)

    async def test_home_rejects_browser_attempt_to_replace_root(self) -> None:
        client = await self.authenticated_client()
        try:
            response = await client.get("/?root=/tmp/attacker")
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("/tmp/attacker", response.text)


if __name__ == "__main__":
    unittest.main()
