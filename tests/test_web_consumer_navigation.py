from __future__ import annotations

import unittest

from tests.web_consumer_support import ConsumerWebFixture


class ConsumerNavigationTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_navigation_and_settings_are_truthful(self) -> None:
        client = await self.authenticated_client()
        try:
            responses = {
                path: await client.get(path)
                for path in ("/", "/duplicates", "/organize", "/attention", "/scans", "/settings", "/review/advanced")
            }
        finally:
            await client.aclose()

        for response in responses.values():
            self.assertEqual(response.status_code, 200)
        for label in ("Home", "Duplicates", "Organize", "Scans", "Settings"):
            self.assertIn(f">{label}</a>", responses["/"].text)
        self.assertNotIn('href="/attention" aria-current', responses["/"].text)
        self.assertIn('href="/duplicates" aria-current="page"', responses["/duplicates"].text)
        self.assertIn('href="/organize" aria-current="page"', responses["/organize"].text)
        self.assertIn('href="/scans" aria-current="page"', responses["/scans"].text)
        self.assertIn('href="/settings" aria-current="page"', responses["/settings"].text)
        self.assertIn("Local only on this computer", responses["/settings"].text)
        self.assertIn("Cloud services", responses["/settings"].text)
        self.assertNotIn("<form", responses["/settings"].text)

    async def test_old_review_route_redirects_and_preserves_valid_query(self) -> None:
        client = await self.authenticated_client()
        try:
            response = await client.get(
                "/review?category=duplicate&sort=source&direction=desc&page_size=50"
            )
            invalid = await client.get("/review?return_to=https://evil.example")
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 307)
        self.assertTrue(response.headers["location"].startswith("/review/advanced?"))
        self.assertIn("category=duplicate", response.headers["location"])
        self.assertEqual(invalid.status_code, 400)

    async def test_unknown_surfaces_are_rejected(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            decision = await client.post(
                "/review/items/D1/decision?surface=https://evil.example",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            scan = await client.post(
                "/scan?surface=/tmp/path",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            blank_scan = await client.post(
                "/scan?surface=",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            blank = await client.post(
                "/review/items/D1/decision?surface=",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            settings_path = await client.get("/settings?root=/tmp/attacker")
            scans_path = await client.get("/scans?root=/tmp/attacker")
        finally:
            await client.aclose()

        self.assertEqual(decision.status_code, 400)
        self.assertEqual(scan.status_code, 400)
        self.assertEqual(blank_scan.status_code, 400)
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(settings_path.status_code, 400)
        self.assertEqual(scans_path.status_code, 400)
        self.assertEqual(self.decision("D1"), "undecided")


if __name__ == "__main__":
    unittest.main()
