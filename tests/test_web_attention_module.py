from __future__ import annotations

import json
import unittest

from tests.web_consumer_support import ConsumerWebFixture


class WebAttentionModuleTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_attention_queue_is_cautious_and_secondary_row_is_preserved(self) -> None:
        client = await self.authenticated_client()
        try:
            page = await client.get("/attention")
            csrf = await self.csrf(client, "/attention")
            changed = await client.post(
                "/review/items/R2/decision?surface=attention",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(),
            )
            result = await client.get(changed.headers["location"])
        finally:
            await client.aclose()
        self.assertIn("Empty file", page.text)
        self.assertIn("Set aside for review", page.text)
        self.assertNotIn("beta backup copy.txt", page.text)
        self.assertEqual(self.decision("R2"), "approved")
        self.assertEqual(self.decision("R1"), "undecided")
        self.assertIn("Set aside for review. No file has moved yet.", result.text)
        self.assertIn("Total findings</dt><dd>2", result.text)

    async def test_attention_artifact_includes_primary_and_secondary_rows(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/attention")
            saved = await client.post(
                "/attention/save",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()
        data = json.loads(
            (
                self.root
                / "AI_Review"
                / "review_sessions"
                / "attention_reviewed_plan.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(saved.status_code, 303)
        self.assertEqual({row["id"] for row in data["items"]}, {"R1", "R2"})
        self.assertTrue(all(row["decision"] == "undecided" for row in data["items"]))


if __name__ == "__main__":
    unittest.main()
