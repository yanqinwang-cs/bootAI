from __future__ import annotations

import unittest

from tests.web_consumer_support import ConsumerWebFixture


class AttentionWorkflowTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_attention_shows_only_primary_attention_cards(self) -> None:
        client = await self.authenticated_client()
        try:
            page = await client.get("/attention")
        finally:
            await client.aclose()

        self.assertEqual(page.status_code, 200)
        self.assertIn("empty.txt", page.text)
        self.assertIn("Empty file", page.text)
        self.assertIn("Set aside for review", page.text)
        self.assertIn("Leave here", page.text)
        self.assertIn("Skip for now", page.text)
        self.assertNotIn("beta backup copy.txt", page.text)
        self.assertNotIn("exact copy", page.text)

    async def test_attention_feedback_never_claims_movement(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/attention")
            response = await client.post(
                "/review/items/R2/decision?surface=attention&page=1",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(),
            )
            page = await client.get(response.headers["location"])
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 303)
        self.assertIn("Set aside for review. No file has moved.", page.text)
        self.assertIn("This step is not available in the web app yet", page.text)
        self.assertNotIn(">Apply<", page.text)
        self.assertNotIn("Apply changes", page.text)
        self.assertEqual(self.decision("R2"), "approved")


if __name__ == "__main__":
    unittest.main()
