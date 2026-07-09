from pathlib import Path
import json
import tempfile
import unittest

from organizer.html_report import render_html_report
from organizer.reports import build_scan_report
from organizer.rule_audit import _expansion_warnings


class RuleAuditTests(unittest.TestCase):
    def test_no_rules_file_reports_unloaded_and_creates_no_rules_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CS1010X-lec1.pdf").write_text("x", encoding="utf-8")

            report = build_scan_report(root)
            audit = report["rule_audit"]

            self.assertFalse(audit["rules_loaded"])
            self.assertIsNone(audit["rules_path"])
            self.assertEqual(audit["rule_effects"], [])
            self.assertIn("Rule-aware audit was skipped", audit["warnings"][0])
            self.assertFalse((root / "AI_Review" / "config" / "organization_rules.json").exists())
            self.assertNotIn("plan_items", audit)

    def test_invalid_rules_file_is_not_modified_and_audit_is_unloaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "AI_Review" / "config" / "organization_rules.json"
            rules_path.parent.mkdir(parents=True)
            rules_path.write_text("{invalid", encoding="utf-8")
            original = rules_path.read_text(encoding="utf-8")
            (root / "CS1010X-lec1.pdf").write_text("x", encoding="utf-8")

            report = build_scan_report(root)
            audit = report["rule_audit"]

            self.assertFalse(audit["rules_loaded"])
            self.assertEqual(audit["rules_path"], "AI_Review/config/organization_rules.json")
            self.assertTrue(any("invalid" in warning.lower() or "unloaded" in warning.lower() for warning in audit["warnings"]))
            self.assertEqual(rules_path.read_text(encoding="utf-8"), original)

    def test_rules_loaded_reflects_loaded_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_rules(
                root,
                {
                    "version": 1,
                    "locked_anchors": ["CS1010X"],
                    "ignored_terms": ["Python"],
                    "anchor_aliases": {"programming methodology": "CS1010X"},
                    "preferred_granularities": ["course_code"],
                },
            )
            rules_path = root / "AI_Review" / "config" / "organization_rules.json"
            original_rules = rules_path.read_text(encoding="utf-8")
            (root / "CS1010X-lec1.pdf").write_text("x", encoding="utf-8")
            (root / "CS1010X-lec2.pdf").write_text("x", encoding="utf-8")
            (root / "Python notes.pdf").write_text("x", encoding="utf-8")
            (root / "Python slides.pdf").write_text("x", encoding="utf-8")

            audit = build_scan_report(root)["rule_audit"]

            self.assertTrue(audit["rules_loaded"])
            self.assertEqual(audit["rules_path"], "AI_Review/config/organization_rules.json")
            self.assertEqual(audit["locked_anchors"], ["CS1010X"])
            self.assertEqual(audit["ignored_terms"], ["Python"])
            self.assertEqual(audit["anchor_aliases"], {"programming methodology": "CS1010X"})
            self.assertEqual(audit["preferred_granularities"], ["course_code"])
            self.assertEqual(rules_path.read_text(encoding="utf-8"), original_rules)

    def test_locked_anchor_effect_records_before_after_and_match_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_rules(root, {"version": 1, "locked_anchors": ["CS1010X"]})
            for name in ["CS1010X-lec1.pdf", "CS1010X-lec2.pdf", "CS1010X-final.pdf"]:
                (root / name).write_text("x", encoding="utf-8")

            effects = build_scan_report(root)["rule_audit"]["rule_effects"]
            effect = next(item for item in effects if item["rule_type"] == "locked_anchor")

            self.assertEqual(effect["value"], "CS1010X")
            self.assertGreater(effect["matched_file_count"], 0)
            self.assertIn(effect["before_decision"], {"needs_decision", "suggested", None})
            self.assertEqual(effect["after_decision"], "locked_anchor")

    def test_broad_locked_anchor_warning_is_high_risk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_rules(root, {"version": 1, "locked_anchors": ["CS1010X"]})
            for index in range(52):
                (root / f"CS1010X document {index:02d}.pdf").write_text("x", encoding="utf-8")

            effect = next(
                item
                for item in build_scan_report(root)["rule_audit"]["rule_effects"]
                if item["rule_type"] == "locked_anchor"
            )

            self.assertEqual(effect["risk_level"], "high")
            self.assertIn("Review generated organization suggestions", effect["warning"])

    def test_ignored_term_alias_and_preferred_granularity_effects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_rules(
                root,
                {
                    "version": 1,
                    "ignored_terms": ["Python"],
                    "anchor_aliases": {"programming methodology": "CS1010X"},
                    "preferred_granularities": ["course_code"],
                },
            )
            (root / "Python notes.pdf").write_text("x", encoding="utf-8")
            (root / "Python slides.pdf").write_text("x", encoding="utf-8")

            effects = build_scan_report(root)["rule_audit"]["rule_effects"]
            by_type = {item["rule_type"]: item for item in effects}

            self.assertEqual(by_type["ignored_term"]["value"], "Python")
            self.assertEqual(
                by_type["anchor_alias"]["value"],
                {"alias": "programming methodology", "canonical": "CS1010X"},
            )
            self.assertEqual(by_type["preferred_granularity"]["value"], "course_code")
            self.assertIn("advisory metadata", by_type["preferred_granularity"]["effect"])
            self.assertEqual(by_type["preferred_granularity"]["risk_level"], "none")

    def test_before_after_counts_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_rules(root, {"version": 1, "locked_anchors": ["CS1010X"]})
            for name in ["CS1010X-lec1.pdf", "CS1010X-lec2.pdf"]:
                (root / name).write_text("x", encoding="utf-8")

            counts = build_scan_report(root)["rule_audit"]["before_after_counts"]

            for key in [
                "needs_decision_before",
                "needs_decision_after",
                "suggested_groups_before",
                "suggested_groups_after",
                "ignored_terms_before",
                "ignored_terms_after",
                "organization_suggestions_before",
                "organization_suggestions_after",
            ]:
                self.assertIsInstance(counts[key], int)

    def test_expansion_warning_helper(self) -> None:
        warnings = _expansion_warnings(
            {
                "suggested_groups_before": 10,
                "suggested_groups_after": 40,
                "organization_suggestions_before": 10,
                "organization_suggestions_after": 41,
            }
        )

        self.assertEqual(len(warnings), 2)
        self.assertTrue(all("Review rules" in warning for warning in warnings))

    def test_html_renders_rule_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_rules(root, {"version": 1, "locked_anchors": ["CS1010X"]})
            for name in ["CS1010X-lec1.pdf", "CS1010X-lec2.pdf"]:
                (root / name).write_text("x", encoding="utf-8")

            html = render_html_report(build_scan_report(root))

            self.assertIn("Rule-aware organization audit", html)
            self.assertIn("CS1010X", html)
            self.assertIn("Rule effects", html)

    def test_rule_audit_module_has_no_movement_dependencies(self) -> None:
        module_path = Path(__file__).resolve().parents[1] / "src" / "organizer" / "rule_audit.py"
        source = module_path.read_text(encoding="utf-8")

        self.assertNotIn("exec" + "utor", source)
        self.assertNotIn("Move" + "PlanItem", source)

    def _write_rules(self, root: Path, data: dict[str, object]) -> None:
        rules_path = root / "AI_Review" / "config" / "organization_rules.json"
        rules_path.parent.mkdir(parents=True)
        rules_path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
