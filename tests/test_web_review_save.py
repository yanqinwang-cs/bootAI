from __future__ import annotations

import json
from unittest import mock
import unittest

from organizer.review_session import load_reviewed_plan_items
from tests.web_review_support import WebReviewFixture


class WebReviewSaveTests(
    WebReviewFixture,
    unittest.IsolatedAsyncioTestCase,
):
    async def test_explicit_save_writes_all_rows_and_returns_clean_session(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            changed = await client.post(
                "/review/items/D1/decision",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            saved = await client.post(
                "/review/save?category=review_candidate&decision=approved&page_size=2",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            page = await client.get(saved.headers["location"])
        finally:
            await client.aclose()

        paths = sorted(
            (self.root / "AI_Review" / "review_sessions").glob("*.json")
        )
        self.assertEqual(changed.status_code, 303)
        self.assertEqual(saved.status_code, 303)
        self.assertEqual(len(paths), 1)
        data = json.loads(paths[0].read_text(encoding="utf-8"))
        loaded = load_reviewed_plan_items(paths[0], self.root)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["plan_type"], "batch_review")
        self.assertEqual(len(loaded), 7)
        self.assertNotIn("dirty", data)
        self.assertNotIn("filters", data)
        self.assertIn("All review decisions saved", page.text)
        self.assertIn("AI_Review/review_sessions/", page.text)
        self.assertIn("Rows saved: 7", page.text)
        self.assertIn("Approved conflicts: 0", page.text)
        self.assertNotIn(str(self.root), page.text)
        self.assertTrue(
            (self.root / "AI_Review" / "review_state" / "review_decisions.json").is_file()
        )
        self.assertFalse((self.root / "AI_Review" / "operation_logs").exists())

    async def test_saves_are_collision_safe_and_never_overwrite(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            first = await client.post(
                "/review/save",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            second = await client.post(
                "/review/save",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()

        paths = sorted(
            path.name
            for path in (self.root / "AI_Review" / "review_sessions").glob("*.json")
        )
        self.assertEqual(first.status_code, 303)
        self.assertEqual(second.status_code, 303)
        self.assertEqual(len(paths), 2)
        self.assertNotEqual(paths[0], paths[1])
        self.assertTrue(all(name.endswith("_reviewed_plan.json") for name in paths))

    async def test_decisions_never_autosave_and_browser_cannot_choose_path(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            decision = await client.post(
                "/review/items/D1/decision",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            chosen_path = await client.post(
                "/review/save",
                data={
                    "csrf_token": csrf,
                    "output_path": "/tmp/attacker.json",
                },
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()

        self.assertEqual(decision.status_code, 303)
        self.assertEqual(chosen_path.status_code, 400)
        self.assertFalse((self.root / "AI_Review" / "review_sessions").exists())

    async def test_failed_save_keeps_session_dirty_and_reports_no_path(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            await client.post(
                "/review/items/D1/decision",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            with mock.patch(
                "organizer.web.review_explorer.save_review_session",
                side_effect=OSError("sensitive detail"),
            ):
                failed = await client.post(
                    "/review/save",
                    data={"csrf_token": csrf},
                    headers=self.origin_headers(),
                )
            page = await client.get("/review/advanced")
        finally:
            await client.aclose()

        self.assertEqual(failed.status_code, 500)
        self.assertNotIn("sensitive detail", failed.text)
        self.assertNotIn("Saved reviewed plan", failed.text)
        self.assertIn("Unsaved review changes", page.text)
        self.assertFalse((self.root / "AI_Review" / "review_sessions").exists())


if __name__ == "__main__":
    unittest.main()
