from __future__ import annotations

import re
import unittest

from tests.web_review_support import WebReviewFixture


class WebReviewBulkDecisionTests(
    WebReviewFixture,
    unittest.IsolatedAsyncioTestCase,
):
    async def test_preview_respects_filter_sort_page_and_exposes_no_paths_in_token(self) -> None:
        client = await self.authenticated_client()
        query = "category=review_candidate&sort=source&direction=desc&page=2&page_size=2"
        try:
            csrf = await self.csrf(client, f"/review/advanced?{query}")
            response = await client.post(
                f"/review/page-decision/preview?{query}",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()

        token = _hidden(response.text, "preview_token")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Current page</dt><dd>2 of 3", response.text)
        self.assertIn("Matching rows</dt><dd>6", response.text)
        self.assertIn("Targeted rows</dt><dd>2", response.text)
        self.assertIn("Rows that will change</dt><dd>2", response.text)
        self.assertIn("Stable IDs", response.text)
        self.assertNotIn(str(self.root), token)
        self.assertNotIn("backup copy", token)
        self.assertNotIn('name="source"', response.text)
        self.assertNotIn('name="destination"', response.text)

    async def test_exact_confirmations_apply_frozen_targets_and_replay_fails(self) -> None:
        actions = (
            ("rejected", "REJECT CURRENT PAGE", "Keep here"),
            ("undecided", "UNDECIDE CURRENT PAGE", "Review later"),
            ("approved", "APPROVE CURRENT PAGE", "Organize"),
        )
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            for decision, phrase, label in actions:
                preview = await client.post(
                    "/review/page-decision/preview?category=review_candidate&page_size=2",
                    data={"csrf_token": csrf, "decision": decision},
                    headers=self.origin_headers(),
                )
                token = _hidden(preview.text, "preview_token")
                confirmed = await client.post(
                    "/review/page-decision/confirm",
                    data={
                        "csrf_token": csrf,
                        "preview_token": token,
                        "confirmation": phrase,
                    },
                    headers=self.origin_headers(),
                )
                replay = await client.post(
                    "/review/page-decision/confirm",
                    data={
                        "csrf_token": csrf,
                        "preview_token": token,
                        "confirmation": phrase,
                    },
                    headers=self.origin_headers(),
                )
                page = await client.get(confirmed.headers["location"])

                self.assertEqual(confirmed.status_code, 303)
                self.assertEqual(replay.status_code, 400)
                self.assertIn(f"Current: <strong>{label}</strong>", page.text)
        finally:
            await client.aclose()

    async def test_wrong_blank_tampered_and_browser_ids_change_nothing(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            for confirmation in ("WRONG", ""):
                preview = await client.post(
                    "/review/page-decision/preview?page_size=2",
                    data={"csrf_token": csrf, "decision": "rejected"},
                    headers=self.origin_headers(),
                )
                token = _hidden(preview.text, "preview_token")
                response = await client.post(
                    "/review/page-decision/confirm",
                    data={
                        "csrf_token": csrf,
                        "preview_token": token,
                        "confirmation": confirmation,
                    },
                    headers=self.origin_headers(),
                )
                self.assertEqual(response.status_code, 400)

            tampered = await client.post(
                "/review/page-decision/confirm",
                data={
                    "csrf_token": csrf,
                    "preview_token": "tampered",
                    "confirmation": "REJECT CURRENT PAGE",
                },
                headers=self.origin_headers(),
            )
            injected_ids = await client.post(
                "/review/page-decision/preview?page_size=2",
                data={
                    "csrf_token": csrf,
                    "decision": "rejected",
                    "ids": "D1,R1",
                },
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()

        self.assertEqual(tampered.status_code, 400)
        self.assertEqual(injected_ids.status_code, 400)
        snapshot = self.app.state.review_explorer.snapshot(
            self.app.state.scan_jobs.snapshot()
        )
        assert snapshot.session is not None
        self.assertFalse(snapshot.session.dirty)

    async def test_preview_and_confirmation_require_csrf_and_same_origin(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            missing_csrf = await client.post(
                "/review/page-decision/preview",
                data={"decision": "rejected"},
                headers=self.origin_headers(),
            )
            external_origin = await client.post(
                "/review/page-decision/preview",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers={"Origin": "http://evil.example"},
            )
            valid = await client.post(
                "/review/page-decision/preview",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            confirm_external_origin = await client.post(
                "/review/page-decision/confirm",
                data={
                    "csrf_token": csrf,
                    "preview_token": _hidden(valid.text, "preview_token"),
                    "confirmation": "REJECT CURRENT PAGE",
                },
                headers={"Origin": "http://evil.example"},
            )
        finally:
            await client.aclose()

        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(external_origin.status_code, 403)
        self.assertEqual(confirm_external_origin.status_code, 403)

    async def test_empty_and_fully_idempotent_pages_do_not_prompt(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            empty = await client.post(
                "/review/page-decision/preview?category=organization",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(),
            )
            idempotent = await client.post(
                "/review/page-decision/preview?category=duplicate",
                data={"csrf_token": csrf, "decision": "approved"},
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()

        self.assertIn("No rows are displayed", empty.text)
        self.assertNotIn('name="confirmation"', empty.text)
        self.assertIn("No changes are required", idempotent.text)
        self.assertNotIn('name="confirmation"', idempotent.text)

    async def test_decision_filter_page_is_clamped_after_confirm(self) -> None:
        client = await self.authenticated_client()
        query = "category=review_candidate&decision=approved&page=3&page_size=2"
        try:
            csrf = await self.csrf(client, f"/review/advanced?{query}")
            preview = await client.post(
                f"/review/page-decision/preview?{query}",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            confirmed = await client.post(
                "/review/page-decision/confirm",
                data={
                    "csrf_token": csrf,
                    "preview_token": _hidden(preview.text, "preview_token"),
                    "confirmation": "REJECT CURRENT PAGE",
                },
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()

        self.assertEqual(confirmed.status_code, 303)
        self.assertIn("decision=approved", confirmed.headers["location"])
        self.assertIn("page=2", confirmed.headers["location"])

    async def test_preview_is_rejected_after_scan_generation_changes(self) -> None:
        client = await self.authenticated_client()
        try:
            csrf = await self.csrf(client)
            preview = await client.post(
                "/review/page-decision/preview?page_size=2",
                data={"csrf_token": csrf, "decision": "rejected"},
                headers=self.origin_headers(),
            )
            self.controller._snapshot = self.controller._snapshot.__class__(
                status="completed",
                job_id="generation-two",
                result=self.result,
            )
            response = await client.post(
                "/review/page-decision/confirm",
                data={
                    "csrf_token": csrf,
                    "preview_token": _hidden(preview.text, "preview_token"),
                    "confirmation": "REJECT CURRENT PAGE",
                },
                headers=self.origin_headers(),
            )
        finally:
            await client.aclose()
        self.assertEqual(response.status_code, 400)


def _hidden(html: str, name: str) -> str:
    match = re.search(rf'name="{name}" value="([^"]*)"', html)
    if match is None:
        raise AssertionError(f"hidden field {name} was not rendered")
    return match.group(1)


if __name__ == "__main__":
    unittest.main()
