from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from organizer.application.review_service import (
    change_review_decisions,
    create_fresh_web_review_session_from_scan_result,
    create_review_session,
    create_review_session_from_scan_result,
    dirty_review_modules,
    review_module_category,
    review_module_is_dirty,
    review_module_items,
    save_review_module,
    save_review_session,
    resume_review_session,
)
from organizer.application.scan_service import scan_root
from organizer.application.view_models import ReviewModule
from organizer.review_session import load_reviewed_plan_items


class ApplicationReviewModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / "alpha.txt").write_text("same", encoding="utf-8")
        (self.root / "beta copy.txt").write_text("same", encoding="utf-8")
        (self.root / "EvoSim_project_slides.pptx").write_text("notes", encoding="utf-8")
        (self.root / "EvoSim_project_slides_final.pptx").write_text("report", encoding="utf-8")
        (self.root / "empty.txt").write_text("", encoding="utf-8")
        self.result = scan_root(self.root)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_fresh_web_policy_maps_every_memory_state_and_starts_clean(self) -> None:
        legacy = create_review_session_from_scan_result(self.result)
        statuses = (
            "new_suggestion",
            "stale_prior_decision",
            "approved_remembered",
            "rejected_remembered",
        )
        decisions = ("approved", "approved", "approved", "rejected")
        items = tuple(
            replace(
                legacy.items[index % len(legacy.items)],
                id=f"X{index + 1}",
                memory_status=status,
                decision=decision,
            )
            for index, (status, decision) in enumerate(zip(statuses, decisions))
        )
        staged = replace(legacy, items=items)
        with mock.patch(
            "organizer.application.review_service.create_review_session_from_scan_result",
            return_value=staged,
        ):
            fresh = create_fresh_web_review_session_from_scan_result(self.result)

        self.assertEqual(
            tuple(item.decision for item in fresh.items),
            ("undecided", "undecided", "approved", "rejected"),
        )
        self.assertEqual(tuple(item.memory_status for item in fresh.items), statuses)
        self.assertFalse(fresh.dirty)

    def test_legacy_report_adapter_keeps_cli_compatible_defaults(self) -> None:
        legacy = create_review_session_from_scan_result(self.result)
        self.assertTrue(legacy.items)
        self.assertTrue(all(item.decision == "approved" for item in legacy.items))
        cli_session = create_review_session(self.root)
        self.assertTrue(all(item.decision == "approved" for item in cli_session.items))

    def test_module_mapping_is_strict_and_rows_are_complete(self) -> None:
        session = create_fresh_web_review_session_from_scan_result(self.result)
        self.assertEqual(review_module_category(ReviewModule.DUPLICATES), "duplicate")
        self.assertEqual(review_module_category(ReviewModule.ORGANIZATION), "organization")
        self.assertEqual(review_module_category(ReviewModule.ATTENTION), "review_candidate")
        with self.assertRaises(ValueError):
            review_module_category("duplicates")  # type: ignore[arg-type]
        for module in ReviewModule:
            category = review_module_category(module)
            self.assertEqual(
                {item.category for item in review_module_items(session, module)},
                {category} if review_module_items(session, module) else set(),
            )

    def test_module_save_updates_only_its_baseline_and_uses_existing_schema(self) -> None:
        session = create_fresh_web_review_session_from_scan_result(self.result)
        duplicate_id = review_module_items(session, ReviewModule.DUPLICATES)[0].id
        organization_id = review_module_items(session, ReviewModule.ORGANIZATION)[0].id
        session = change_review_decisions(session, (duplicate_id,), "approved").session
        session = change_review_decisions(session, (organization_id,), "rejected").session

        result = save_review_module(session, ReviewModule.DUPLICATES)
        self.assertFalse(review_module_is_dirty(result.session, ReviewModule.DUPLICATES))
        self.assertTrue(review_module_is_dirty(result.session, ReviewModule.ORGANIZATION))
        self.assertEqual(dirty_review_modules(result.session), (ReviewModule.ORGANIZATION,))
        self.assertEqual(result.reviewed_plan_path.name, "duplicate_reviewed_plan.json")
        data = json.loads(result.reviewed_plan_path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["plan_type"], "batch_review")
        loaded = load_reviewed_plan_items(result.reviewed_plan_path, self.root)
        self.assertEqual({item.category for item in loaded}, {"duplicate"})
        self.assertEqual(len(loaded), len(review_module_items(session, ReviewModule.DUPLICATES)))

        second = save_review_module(result.session, ReviewModule.DUPLICATES)
        self.assertEqual(second.reviewed_plan_path.name, "duplicate_reviewed_plan_1.json")

    def test_untouched_module_has_no_approved_new_rows_or_review_memory(self) -> None:
        session = create_fresh_web_review_session_from_scan_result(self.result)
        result = save_review_module(session, ReviewModule.ORGANIZATION)
        loaded = load_reviewed_plan_items(result.reviewed_plan_path, self.root)
        self.assertTrue(loaded)
        self.assertTrue(all(item.decision == "undecided" for item in loaded))
        state_data = json.loads(result.review_state_path.read_text(encoding="utf-8"))
        self.assertEqual(state_data["decisions"], [])
        resumed = resume_review_session(self.root, result.reviewed_plan_path)
        self.assertTrue(all(item.decision == "undecided" for item in resumed.items))

    def test_explicit_eligible_choice_is_written_through_existing_review_policy(self) -> None:
        session = create_fresh_web_review_session_from_scan_result(self.result)
        item = review_module_items(session, ReviewModule.ORGANIZATION)[0]
        chosen = change_review_decisions(session, (item.id,), "approved").session
        result = save_review_module(chosen, ReviewModule.ORGANIZATION)
        state_data = json.loads(result.review_state_path.read_text(encoding="utf-8"))
        self.assertEqual(len(state_data["decisions"]), 1)
        self.assertEqual(state_data["decisions"][0]["decision"], "approved")
        self.assertEqual(state_data["decisions"][0]["category"], "organization")

    def test_full_save_after_partial_save_clears_every_module(self) -> None:
        session = create_fresh_web_review_session_from_scan_result(self.result)
        for module in ReviewModule:
            rows = review_module_items(session, module)
            if rows:
                session = change_review_decisions(
                    session, (rows[0].id,), "rejected"
                ).session
        partial = save_review_module(session, ReviewModule.DUPLICATES)
        full = save_review_session(partial.session)
        self.assertFalse(full.session.dirty)
        self.assertEqual(dirty_review_modules(full.session), ())

    def test_failed_module_save_leaves_original_session_dirty(self) -> None:
        session = create_fresh_web_review_session_from_scan_result(self.result)
        item = review_module_items(session, ReviewModule.DUPLICATES)[0]
        dirty = change_review_decisions(session, (item.id,), "approved").session
        with mock.patch(
            "organizer.application.review_service.save_reviewed_plan",
            side_effect=OSError("failed"),
        ):
            with self.assertRaises(OSError):
                save_review_module(dirty, ReviewModule.DUPLICATES)
        self.assertTrue(review_module_is_dirty(dirty, ReviewModule.DUPLICATES))
        self.assertEqual(dirty.module_saved_paths, ())


if __name__ == "__main__":
    unittest.main()
