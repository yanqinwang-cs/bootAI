from __future__ import annotations

import unittest

from tests.web_consumer_support import ConsumerWebFixture


class WebOrganizationModuleTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_organization_queue_advances_one_card_at_a_time(self) -> None:
        client = await self.authenticated_client()
        try:
            first = await client.get("/organize")
            csrf = await self.csrf(client, "/organize")
            changed = await client.post(
                "/review/items/O1/decision?surface=organize",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(**{"HX-Request": "true"}),
            )
        finally:
            await client.aclose()
        self.assertIn("EvoSim_project_slides.pptx", first.text)
        self.assertNotIn("card-heading-O2", first.text)
        self.assertIn("card-heading-O2", changed.text)
        self.assertIn("Added to organization choices", changed.text)
        self.assertIn("Organized", changed.text)
        self.assertEqual(self.decision("O1"), "approved")
        self.assertEqual(self.decision("O2"), "undecided")

    async def test_forged_non_current_card_is_rejected(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/organize")
            response = await client.post(
                "/review/items/O2/decision?surface=organize",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.decision("O1"), "undecided")
        self.assertEqual(self.decision("O2"), "undecided")


if __name__ == "__main__":
    unittest.main()
