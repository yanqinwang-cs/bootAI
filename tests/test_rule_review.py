from __future__ import annotations

import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from organizer.models import RuleCandidate
from organizer.organization_rules import ORGANIZATION_RULES_RELATIVE_PATH
from organizer.reports import build_scan_report, write_report
from organizer.rule_review import (
    DECISION_ACCEPT,
    DECISION_REJECT,
    RULE_REVIEW_DIR,
    apply_rule_decisions,
    export_rule_candidates,
    load_reviewed_rule_file,
    rule_candidates_from_report,
)


class RuleReviewTests(unittest.TestCase):
    def test_export_rule_candidates_uses_deterministic_ids_and_no_rules_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "cs1010x finals"
            folder.mkdir()
            (folder / "cs1010x-final-jun21.pdf").write_text("x", encoding="utf-8")
            (folder / "cs1010x-final-solutions-jun21.pdf").write_text("x", encoding="utf-8")

            candidates = rule_candidates_from_report(build_scan_report(root))
            output = export_rule_candidates(candidates, root)
            data = json.loads(output.read_text(encoding="utf-8"))

            self.assertTrue(output.exists())
            self.assertFalse((root / ORGANIZATION_RULES_RELATIVE_PATH).exists())
            self.assertTrue(data["candidates"])
            self.assertTrue(
                all(item["candidate_id"] for item in data["candidates"])
            )
            self.assertTrue(
                all(item["decision"] == "undecided" for item in data["candidates"])
            )
            self.assertTrue(
                any(
                    item["candidate_id"] == "lock-anchor-cs1010x"
                    for item in data["candidates"]
                )
            )

    def test_export_rule_candidates_does_not_overwrite_default_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = RuleCandidate(
                candidate_id="lock-anchor-cs1010x",
                rule_type="lock_anchor_candidate",
                value="CS1010X",
                confidence=90,
                reason="test",
            )

            first = export_rule_candidates([candidate], root)
            second = export_rule_candidates([candidate], root)

            self.assertNotEqual(first, second)
            self.assertEqual(first.name, "organization_rule_candidates.json")
            self.assertEqual(second.name, "organization_rule_candidates_1.json")

    def test_custom_export_path_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / RULE_REVIEW_DIR / "custom.json"
            destination.parent.mkdir(parents=True)
            destination.write_text("existing", encoding="utf-8")

            with self.assertRaises(ValueError):
                export_rule_candidates([], root, destination)

    def test_invalid_candidate_ids_and_duplicate_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for candidate_id in ["bad/id", "bad\\id", "bad..id"]:
                path = self._write_review_file(
                    root,
                    [
                        {
                            "candidate_id": candidate_id,
                            "rule_type": "lock_anchor_candidate",
                            "value": "CS1010X",
                            "confidence": 90,
                            "reason": "test",
                            "evidence_paths": [],
                            "decision": "accept",
                        }
                    ],
                )
                with self.assertRaises(ValueError):
                    load_reviewed_rule_file(path, root)

            duplicate_path = self._write_review_file(
                root,
                [
                    self._candidate("lock-anchor-cs1010x", "CS1010X"),
                    self._candidate("lock-anchor-cs1010x", "CS1010X"),
                ],
            )
            with self.assertRaises(ValueError):
                load_reviewed_rule_file(duplicate_path, root)

    def test_unknown_decision_and_unsafe_evidence_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_decision = self._write_review_file(
                root,
                [self._candidate("lock-anchor-cs1010x", "CS1010X", decision="maybe")],
            )
            with self.assertRaises(ValueError):
                load_reviewed_rule_file(bad_decision, root)

            bad_path = self._write_review_file(
                root,
                [
                    {
                        **self._candidate("lock-anchor-cs1010x", "CS1010X"),
                        "evidence_paths": ["../escape"],
                    }
                ],
            )
            with self.assertRaises(ValueError):
                load_reviewed_rule_file(bad_path, root)

    def test_cli_apply_requires_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write_review_file(
                root,
                [self._candidate("lock-anchor-cs1010x", "CS1010X")],
            )
            env = dict(os.environ)
            env["PYTHONPATH"] = "src"

            missing = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "organizer.cli",
                    str(root),
                    "--apply-rule-decisions",
                    str(path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(missing.returncode, 0)
            self.assertIn("refused", missing.stdout)
            self.assertFalse((root / ORGANIZATION_RULES_RELATIVE_PATH).exists())

            wrong = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "organizer.cli",
                    str(root),
                    "--apply-rule-decisions",
                    str(path),
                    "--confirm",
                    "WRONG",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(wrong.returncode, 0)
            self.assertIn("refused", wrong.stdout)
            self.assertFalse((root / ORGANIZATION_RULES_RELATIVE_PATH).exists())

    def test_cli_export_and_exact_confirmed_apply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "cs1010x finals"
            folder.mkdir()
            (folder / "cs1010x-final-jun21.pdf").write_text("x", encoding="utf-8")
            (folder / "cs1010x-final-solutions-jun21.pdf").write_text("x", encoding="utf-8")
            env = dict(os.environ)
            env["PYTHONPATH"] = "src"

            export = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "organizer.cli",
                    str(root),
                    "--export-rule-candidates",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(export.returncode, 0, export.stderr)
            candidate_path = root / RULE_REVIEW_DIR / "organization_rule_candidates.json"
            self.assertTrue(candidate_path.exists())
            data = json.loads(candidate_path.read_text(encoding="utf-8"))
            data["candidates"][0]["decision"] = "accept"
            reviewed_path = root / RULE_REVIEW_DIR / "organization_rule_candidates.reviewed.json"
            reviewed_path.write_text(json.dumps(data), encoding="utf-8")

            apply = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "organizer.cli",
                    str(root),
                    "--apply-rule-decisions",
                    str(reviewed_path),
                    "--confirm",
                    "APPLY ORGANIZATION RULES",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(apply.returncode, 0, apply.stderr)
            self.assertIn("No files were moved", apply.stdout)
            self.assertTrue((root / ORGANIZATION_RULES_RELATIVE_PATH).exists())

    def test_apply_accepted_lock_anchor_writes_rules_and_result_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write_review_file(
                root,
                [self._candidate("lock-anchor-cs1010x", "CS1010X")],
            )

            result_path = apply_rule_decisions(path, root)
            rules = json.loads((root / ORGANIZATION_RULES_RELATIVE_PATH).read_text(encoding="utf-8"))
            result = json.loads(result_path.read_text(encoding="utf-8"))

            self.assertEqual(rules["locked_anchors"], ["CS1010X"])
            self.assertEqual(result["applied"][0]["candidate_id"], "lock-anchor-cs1010x")
            self.assertFalse(hasattr(result, "plan_items"))

    def test_apply_ignored_term_alias_and_preferred_granularity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write_review_file(
                root,
                [
                    {
                        **self._candidate("ignore-term-python", "Python"),
                        "rule_type": "ignore_term_candidate",
                    },
                    {
                        **self._candidate("alias-cs1010x-programming-methodology", "unused"),
                        "rule_type": "alias_candidate",
                        "value": {
                            "alias": "programming methodology",
                            "canonical": "CS1010X",
                        },
                    },
                    {
                        **self._candidate("preferred-granularity-course-code", "course_code"),
                        "rule_type": "preferred_granularity_candidate",
                    },
                ],
            )

            apply_rule_decisions(path, root)
            rules = json.loads((root / ORGANIZATION_RULES_RELATIVE_PATH).read_text(encoding="utf-8"))

            self.assertEqual(rules["ignored_terms"], ["Python"])
            self.assertEqual(
                rules["anchor_aliases"],
                {"programming methodology": "CS1010X"},
            )
            self.assertEqual(rules["preferred_granularities"], ["course_code"])

    def test_alias_conflict_does_not_overwrite_existing_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / ORGANIZATION_RULES_RELATIVE_PATH
            config.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "locked_anchors": [],
                        "ignored_terms": [],
                        "anchor_aliases": {"x": "A"},
                    }
                ),
                encoding="utf-8",
            )
            path = self._write_review_file(
                root,
                [
                    {
                        **self._candidate("alias-b-x", "unused"),
                        "rule_type": "alias_candidate",
                        "value": {"alias": "x", "canonical": "B"},
                    }
                ],
            )

            result_path = apply_rule_decisions(path, root)
            rules = json.loads(config.read_text(encoding="utf-8"))
            result = json.loads(result_path.read_text(encoding="utf-8"))

            self.assertEqual(rules["anchor_aliases"], {"x": "A"})
            self.assertEqual(result["applied"], [])
            self.assertTrue(result["warnings"])

    def test_existing_unknown_rule_field_fails_without_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / ORGANIZATION_RULES_RELATIVE_PATH
            config.parent.mkdir(parents=True)
            original = {
                "version": 1,
                "locked_anchors": [],
                "ignored_terms": [],
                "anchor_aliases": {},
                "unexpected": True,
            }
            config.write_text(json.dumps(original), encoding="utf-8")
            path = self._write_review_file(
                root,
                [self._candidate("lock-anchor-cs1010x", "CS1010X")],
            )

            with self.assertRaises(ValueError):
                apply_rule_decisions(path, root)

            self.assertEqual(json.loads(config.read_text(encoding="utf-8")), original)

    def test_rejected_ignored_and_undecided_decisions_do_not_write_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write_review_file(
                root,
                [
                    self._candidate("lock-anchor-a", "A", decision=DECISION_REJECT),
                    self._candidate("lock-anchor-b", "B", decision="ignore_candidate"),
                    self._candidate("lock-anchor-c", "C", decision="undecided"),
                ],
            )

            result_path = apply_rule_decisions(path, root)
            result = json.loads(result_path.read_text(encoding="utf-8"))

            self.assertFalse((root / ORGANIZATION_RULES_RELATIVE_PATH).exists())
            self.assertEqual(result["applied"], [])
            self.assertEqual(len(result["skipped"]), 3)

    def test_ordinary_report_generation_does_not_write_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "EvoSim images"
            folder.mkdir()
            (folder / "EvoSim_project_slides.pptx").write_text("x", encoding="utf-8")
            (folder / "EvoSim_fixed_google_slides.pptx").write_text("x", encoding="utf-8")

            report = build_scan_report(root)
            write_report(report, root)

            self.assertFalse((root / ORGANIZATION_RULES_RELATIVE_PATH).exists())

    def test_rule_review_module_does_not_import_executor_or_move_plan_items(self) -> None:
        module_path = Path(__file__).resolve().parents[1] / "src" / "organizer" / "rule_review.py"
        source = module_path.read_text(encoding="utf-8")

        self.assertNotIn("executor", source)
        self.assertNotIn("MovePlanItem", source)

    def _candidate(
        self,
        candidate_id: str,
        value: str,
        decision: str = DECISION_ACCEPT,
    ) -> dict[str, object]:
        return {
            "candidate_id": candidate_id,
            "rule_type": "lock_anchor_candidate",
            "value": value,
            "confidence": 90,
            "reason": "test",
            "evidence_paths": [],
            "suggested_action": "review",
            "decision": decision,
            "note": "",
        }

    def _write_review_file(
        self,
        root: Path,
        candidates: list[dict[str, object]],
    ) -> Path:
        path = root / RULE_REVIEW_DIR / "reviewed.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source": "test",
                    "instructions": "test",
                    "candidates": candidates,
                }
            ),
            encoding="utf-8",
        )
        return path


if __name__ == "__main__":
    unittest.main()
