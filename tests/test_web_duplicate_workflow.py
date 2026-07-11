from __future__ import annotations

import unittest

from tests.web_consumer_support import ConsumerWebFixture


class DuplicateWorkflowTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_card_has_precedence_and_secondary_attention(self) -> None:
        client = await self.authenticated_client()
        try:
            duplicate = await client.get("/duplicates")
            attention = await client.get("/attention")
        finally:
            await client.aclose()

        self.assertEqual(duplicate.status_code, 200)
        self.assertIn("beta backup copy.txt", duplicate.text)
        self.assertIn("This is an exact copy of", duplicate.text)
        self.assertIn("alpha.txt", duplicate.text)
        self.assertIn("Space used by this extra copy", duplicate.text)
        self.assertIn("does not reclaim storage", duplicate.text)
        self.assertIn("Also noticed", duplicate.text)
        self.assertIn("Backup or copy-looking file", duplicate.text)
        self.assertIn("Current choice: Set aside for review", duplicate.text)
        self.assertNotIn("beta backup copy.txt", attention.text)
        self.assertNotIn("EvoSim_project", duplicate.text)

    async def test_duplicate_choice_changes_only_primary_row(self) -> None:
        before_files = self.file_snapshot()
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            response = await client.post(
                "/review/items/D1/decision?surface=duplicates&page=1",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            page = await client.get(response.headers["location"])
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.decision("D1"), "rejected")
        self.assertEqual(self.decision("R1"), "approved")
        self.assertIn("This file will remain in its current folder", page.text)
        self.assertEqual(self.file_snapshot(), before_files)
        self.assertFalse(list(self.root.rglob("*operation_log*.json")))

    async def test_duplicate_surface_rejects_other_and_secondary_rows(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            organization = await client.post(
                "/review/items/O1/decision?surface=duplicates",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            secondary = await client.post(
                "/review/items/R1/decision?surface=attention",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()

        self.assertEqual(organization.status_code, 404)
        self.assertEqual(secondary.status_code, 404)
        self.assertEqual(self.decision("O1"), "approved")
        self.assertEqual(self.decision("R1"), "approved")


if __name__ == "__main__":
    unittest.main()
