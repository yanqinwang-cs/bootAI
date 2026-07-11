from __future__ import annotations

import unittest

import httpx

from tests.web_review_support import WebReviewFixture


class WebReviewDecisionTests(
    WebReviewFixture,
    unittest.IsolatedAsyncioTestCase,
):
    async def test_standard_decision_redirects_and_marks_only_changed_rows_dirty(self) -> None:
        before = self.artifact_paths()
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            response = await client.post(
                "/review/items/D1/decision?category=duplicate&page_size=25",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            page = await client.get(response.headers["location"])
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 303)
        self.assertIn("category=duplicate", response.headers["location"])
        self.assertIn("Unsaved review changes", page.text)
        self.assertIn("Current: <strong>Keep here</strong>", page.text)
        self.assertEqual(before, self.artifact_paths())
        self.assertFalse((self.root / "AI_Review" / "operation_logs").exists())

    async def test_idempotent_decision_stays_clean_and_writes_nothing(self) -> None:
        before = self.artifact_paths()
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            response = await client.post(
                "/review/items/D1/decision",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(),
            )
            page = await client.get(response.headers["location"])
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 303)
        self.assertIn("All review decisions saved", page.text)
        self.assertNotIn("Unsaved review changes", page.text)
        self.assertEqual(before, self.artifact_paths())

    async def test_htmx_returns_only_updated_workspace_and_preserves_view(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client, "/review/advanced?category=duplicate")
            response = await client.post(
                "/review/items/D1/decision?category=duplicate&sort=source&direction=desc&page=1&page_size=25",
                data={"csrf_token": csrf, "decision": "undecided"},
                headers=self.origin_headers(**{"HX-Request": "true"}),
            )
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.text.lstrip().startswith('<div id="review-workspace"'))
        self.assertNotIn("<!doctype html>", response.text)
        self.assertIn("Unsaved review changes", response.text)
        self.assertIn("category=duplicate", response.headers["hx-replace-url"])
        self.assertIn("sort=source", response.headers["hx-replace-url"])

    async def test_mutation_security_and_input_validation_fail_closed(self) -> None:
        unauthenticated = _client(self.app)
        try:
            unauth = await unauthenticated.post(
                "/review/items/D1/decision",
                data={"decision": "rejected"},
                headers=self.origin_headers(),
            )
        finally:
            await unauthenticated.aclose()

        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            cases = [
                ({"decision": "rejected"}, self.origin_headers(), 403),
                (
                    {"csrf_token": "wrong", "decision": "rejected"},
                    self.origin_headers(),
                    403,
                ),
                (
                    {"csrf_token": csrf, "decision": "rejected"},
                    {"Origin": "http://evil.example"},
                    403,
                ),
                (
                    {"csrf_token": csrf, "decision": "maybe"},
                    self.origin_headers(),
                    400,
                ),
                (
                    {
                        "csrf_token": csrf,
                        "decision": "rejected",
                        "source": "/tmp/attacker",
                    },
                    self.origin_headers(),
                    400,
                ),
            ]
            for data, headers, status in cases:
                with self.subTest(data=data):
                    response = await client.post(
                        "/review/items/D1/decision",
                        data=data,
                        headers=headers,
                    )
                    self.assertEqual(response.status_code, status)
            unknown = await client.post(
                "/review/items/UNKNOWN/decision",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()

        self.assertEqual(unauth.status_code, 403)
        self.assertEqual(unknown.status_code, 404)
        snapshot = self.app.state.review_explorer.snapshot(
            self.app.state.scan_jobs.snapshot()
        )
        assert snapshot.session is not None
        self.assertFalse(snapshot.session.dirty)

    async def test_invalid_host_is_rejected_before_review_mutation(self) -> None:
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://evil.example",
            follow_redirects=False,
        )
        try:
            response = await client.post(
                "/review/items/D1/decision",
                data={"csrf_token": "x", "decision": "rejected"},
                headers={"Origin": "http://evil.example"},
            )
        finally:
            await client.aclose()
        self.assertEqual(response.status_code, 400)


def _client(app: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://127.0.0.1",
        follow_redirects=False,
    )


if __name__ == "__main__":
    unittest.main()
