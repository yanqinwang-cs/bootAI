from __future__ import annotations

import json
from unittest import mock
import unittest

from tests.web_consumer_support import ConsumerWebFixture


class WebModuleSavingTests(ConsumerWebFixture, unittest.IsolatedAsyncioTestCase):
    async def test_modules_save_independently_and_full_save_still_works(self) -> None:
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
            duplicate_save = await client.post(
                "/duplicates/save",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            blocked = await client.post(
                "/scan",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            organization_save = await client.post(
                "/organize/save",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            full_save = await client.post(
                "/review/save",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()

        self.assertEqual(duplicate_save.status_code, 303)
        self.assertEqual(organization_save.status_code, 303)
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("Files to organize", blocked.text)
        self.assertEqual(full_save.status_code, 303)
        plans = self.root / "AI_Review" / "review_sessions"
        duplicate = json.loads((plans / "duplicate_reviewed_plan.json").read_text())
        organization = json.loads((plans / "organization_reviewed_plan.json").read_text())
        self.assertEqual({row["category"] for row in duplicate["items"]}, {"duplicate"})
        self.assertEqual({row["category"] for row in organization["items"]}, {"organization"})
        self.assertTrue(any(path.name.endswith("_reviewed_plan.json") for path in plans.glob("*.json") if path.name[0].isdigit()))
        self.assertFalse(self.session().dirty)

    async def test_module_forms_reject_browser_paths_and_bad_security(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            path = await client.post(
                "/duplicates/save",
                data={"csrf_token": csrf, "output_path": "/tmp/evil.json"},
                headers=self.origin_headers(),
            )
            origin = await client.post(
                "/duplicates/save",
                data={"csrf_token": csrf},
                headers={"Origin": "https://evil.example"},
            )
        finally:
            await client.aclose()
        self.assertEqual(path.status_code, 400)
        self.assertEqual(origin.status_code, 403)
        self.assertFalse((self.root / "AI_Review" / "review_sessions").exists())

    async def test_failed_module_save_keeps_only_that_module_dirty(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/duplicates")
            await client.post(
                "/review/items/D1/decision?surface=duplicates",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(),
            )
            with mock.patch(
                "organizer.web.review_explorer.save_review_module",
                side_effect=OSError("sensitive"),
            ):
                failed = await client.post(
                    "/duplicates/save",
                    data={"csrf_token": csrf},
                    headers=self.origin_headers(),
                )
            page = await client.get("/duplicates")
        finally:
            await client.aclose()
        self.assertEqual(failed.status_code, 500)
        self.assertNotIn("sensitive", failed.text)
        self.assertIn("Unsaved changes", page.text)


if __name__ == "__main__":
    unittest.main()
