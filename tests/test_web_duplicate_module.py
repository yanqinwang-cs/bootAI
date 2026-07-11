from __future__ import annotations

import json
import unittest

from tests.web_consumer_support import ConsumerWebFixture


class WebDuplicateModuleTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_guided_duplicate_choice_updates_only_primary_row(self) -> None:
        before = self.file_snapshot()
        client = await self.authenticated_client()
        try:
            page = await client.get("/duplicates")
            csrf = await self.csrf(client, "/duplicates")
            changed = await client.post(
                "/review/items/D1/decision?surface=duplicates",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(),
            )
            result = await client.get(changed.headers["location"])
        finally:
            await client.aclose()

        self.assertIn("0 of 1 reviewed", page.text)
        self.assertIn("Add to duplicate choices", page.text)
        self.assertEqual(self.decision("D1"), "approved")
        self.assertEqual(self.decision("R1"), "undecided")
        self.assertIn("Added to duplicate choices", result.text)
        self.assertIn("All findings reviewed", result.text)
        self.assertEqual(self.file_snapshot(), before)

    async def test_duplicate_save_contains_only_duplicate_rows(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            saved = await client.post(
                "/duplicates/save",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()
        path = self.root / "AI_Review" / "review_sessions" / "duplicate_reviewed_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved.status_code, 303)
        self.assertEqual({item["category"] for item in data["items"]}, {"duplicate"})
        self.assertTrue(all(item["decision"] == "undecided" for item in data["items"]))


if __name__ == "__main__":
    unittest.main()
