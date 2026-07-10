from __future__ import annotations

import unittest

from organizer.web.security import SECURITY_HEADERS
from tests.web_review_support import WebReviewFixture


class WebReviewDirtyStateTests(
    WebReviewFixture,
    unittest.IsolatedAsyncioTestCase,
):
    async def test_view_navigation_and_inspection_do_not_mark_session_dirty(self) -> None:
        client = await self.authenticated_client()
        try:
            clean = await client.get("/review")
            filtered = await client.get(
                "/review?category=review_candidate&sort=source&direction=desc&page_size=2"
            )
            detail = await client.get("/review/items/D1")
            conflicts = await client.get("/review/conflicts")
        finally:
            await client.aclose()

        for response in (clean, filtered):
            self.assertIn('data-review-dirty="false"', response.text)
            self.assertIn("All review decisions saved", response.text)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(conflicts.status_code, 200)
        snapshot = self.app.state.review_explorer.snapshot(
            self.app.state.scan_jobs.snapshot()
        )
        assert snapshot.session is not None
        self.assertFalse(snapshot.session.dirty)

    async def test_dirty_session_blocks_new_scan_without_losing_decisions(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            await client.post(
                "/review/items/D1/decision",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            blocked = await client.post(
                "/scan",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            page = await client.get("/review")
        finally:
            await client.aclose()

        self.assertEqual(blocked.status_code, 409)
        self.assertIn("Save the reviewed plan", blocked.text)
        self.assertIn("did not discard", blocked.text)
        self.assertEqual(self.controller.snapshot().job_id, "generation-one")
        self.assertIn("Current: <strong>Keep here</strong>", page.text)
        self.assertIn("Unsaved review changes", page.text)

    async def test_successful_save_allows_new_scan_and_invalidates_old_session(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            await client.post(
                "/review/items/D1/decision",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            await client.post(
                "/review/save",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            started = await client.post(
                "/scan",
                data={"csrf_token": csrf},
                headers=self.origin_headers(),
            )
            review = await client.get("/review")
        finally:
            await client.aclose()

        self.assertEqual(started.status_code, 303)
        self.assertIn(
            self.controller.snapshot().status,
            {"scanning", "completed"},
        )
        if self.controller.snapshot().status == "scanning":
            self.assertIn("currently running", review.text)
        else:
            snapshot = self.app.state.review_explorer.snapshot(
                self.controller.snapshot()
            )
            assert snapshot.session is not None
            self.assertFalse(snapshot.session.dirty)

    async def test_dirty_marker_and_beforeunload_are_csp_compliant_advisory_only(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            await client.post(
                "/review/items/D1/decision",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            page = await client.get("/review")
            script = await client.get("/static/js/bootai.js")
        finally:
            await client.aclose()

        self.assertIn('data-review-dirty="true"', page.text)
        self.assertIn("Unsaved review changes", page.text)
        self.assertNotIn("onbeforeunload=", page.text)
        self.assertNotIn("<script>", page.text)
        self.assertIn("beforeunload", script.text)
        self.assertNotIn("autosave", script.text.lower())

    async def test_mutation_errors_keep_security_headers_and_no_cors(self) -> None:
        client = await self.authenticated_client()
        try:
            response = await client.post(
                "/review/save",
                data={"csrf_token": "wrong"},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 403)
        for name, value in SECURITY_HEADERS.items():
            self.assertEqual(response.headers[name], value)
        self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
