from __future__ import annotations

import unittest

from tests.web_consumer_support import ConsumerWebFixture


class WebModuleScanBlockingTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_scan_names_every_dirty_module_until_each_is_saved(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            await client.post(
                "/review/items/D1/decision?surface=duplicates",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(),
            )
            await client.post(
                "/review/items/O1/decision?surface=organize",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            both = await client.post(
                "/scan",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            await client.post(
                "/duplicates/save",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            one = await client.post(
                "/scan",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()
        self.assertEqual(both.status_code, 409)
        self.assertIn("Duplicate copies", both.text)
        self.assertIn("Files to organize", both.text)
        self.assertEqual(one.status_code, 409)
        self.assertNotIn("Duplicate copies</li>", one.text)
        self.assertIn("Files to organize", one.text)


if __name__ == "__main__":
    unittest.main()
