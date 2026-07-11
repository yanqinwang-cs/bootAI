from __future__ import annotations

import unittest

from tests.web_consumer_support import ConsumerWebFixture


class WebModuleDirtyStateTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_home_shows_independent_progress_and_persistence(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            await client.post(
                "/review/items/D1/decision?surface=duplicates",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(),
            )
            home = await client.get("/")
            await client.post(
                "/duplicates/save",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            saved_home = await client.get("/")
        finally:
            await client.aclose()
        self.assertIn("All findings reviewed", home.text)
        self.assertIn("Unsaved changes", home.text)
        self.assertIn("Choices saved", saved_home.text)
        self.assertIn("Files to organize", saved_home.text)
        self.assertIn("Not saved yet", saved_home.text)


if __name__ == "__main__":
    unittest.main()
