from __future__ import annotations

import unittest

from tests.web_consumer_support import ConsumerWebFixture


class OrganizeWorkflowTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_organization_cards_are_plain_language_and_isolated(self) -> None:
        client = await self.authenticated_client()
        try:
            page = await client.get("/organize")
        finally:
            await client.aclose()

        self.assertEqual(page.status_code, 200)
        self.assertIn("EvoSim_project_slides.pptx", page.text)
        self.assertNotIn("card-heading-O2", page.text)
        self.assertIn("Add to organization choices", page.text)
        self.assertIn("Leave here", page.text)
        self.assertIn("Skip for now", page.text)
        self.assertNotIn("beta backup copy.txt", page.text)
        self.assertNotIn("empty.txt", page.text)
        self.assertNotIn("MovePlanItem", page.text)

    async def test_organization_htmx_updates_card_feedback_and_summary(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/organize")
            response = await client.post(
                "/review/items/O1/decision?surface=organize&page=1",
                data={"csrf_token": csrf, "decision": "undecided"},
                headers=self.origin_headers(**{"HX-Request": "true"}),
            )
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="consumer-workspace"', response.text)
        self.assertIn("Skipped for now. You can return to it later.", response.text)
        self.assertIn("Organization", response.text)
        self.assertIn("1 skipped for now", response.text)
        self.assertEqual(self.decision("O1"), "undecided")
        self.assertEqual(self.decision("O2"), "undecided")
        self.assertTrue(response.headers["HX-Replace-Url"].startswith("/organize?"))


if __name__ == "__main__":
    unittest.main()
