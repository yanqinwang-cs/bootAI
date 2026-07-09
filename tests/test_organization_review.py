from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from organizer.organization_review import (
    ORGANIZATION_REVIEW_INSTRUCTIONS,
    ORGANIZATION_REVIEW_SOURCE,
    build_organization_review,
    export_organization_review,
    load_organization_review,
    validate_organization_review_data,
)
from organizer.reports import build_scan_report


class OrganizationReviewTests(unittest.TestCase):
    def test_builds_review_rows_from_existing_report_suggestions(self) -> None:
        data = build_organization_review(sample_report())

        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["source"], ORGANIZATION_REVIEW_SOURCE)
        self.assertEqual(data["instructions"], ORGANIZATION_REVIEW_INSTRUCTIONS)
        self.assertEqual(data["scan_root"], ".")
        self.assertTrue(data["rules_loaded"])
        self.assertEqual(
            data["rules_path"],
            "AI_Review/config/organization_rules.json",
        )
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["review_id"], "org-000001")
        self.assertEqual(data["items"][0]["decision"], "undecided")
        self.assertEqual(data["items"][0]["note"], "")

    def test_rows_contain_all_required_fields(self) -> None:
        item = build_organization_review(sample_report())["items"][0]

        self.assertEqual(
            set(item),
            {
                "review_id",
                "source",
                "destination",
                "anchor",
                "evidence",
                "reason",
                "confidence",
                "risk_level",
                "overwrite_risk",
                "decision",
                "note",
            },
        )

    def test_review_ids_are_stable_for_fixed_report(self) -> None:
        report = sample_report()
        report["organization_suggestions"][0]["plan_items"].reverse()

        first = build_organization_review(report)
        second = build_organization_review(report)

        self.assertEqual(
            [(item["review_id"], item["source"]) for item in first["items"]],
            [(item["review_id"], item["source"]) for item in second["items"]],
        )
        self.assertEqual(first["items"][0]["source"], "CS1010X lecture 01.pdf")

    def test_locked_anchor_risk_uses_full_anchor_file_count(self) -> None:
        report = sample_report()
        report["anchor_decisions"]["suggested_groups"][0]["file_count"] = 149
        report["rule_audit"]["rule_effects"][0]["matched_file_count"] = 149

        data = build_organization_review(report)

        self.assertTrue(all(item["risk_level"] == "high" for item in data["items"]))
        self.assertTrue(
            any(
                "Locked anchor CS1010X matched 149 files" in warning
                for warning in data["rule_audit_summary"]["warnings"]
            )
        )

    def test_locked_anchor_risk_thresholds(self) -> None:
        for file_count, expected in [(10, "low"), (11, "medium"), (50, "medium"), (51, "high")]:
            with self.subTest(file_count=file_count):
                report = sample_report()
                report["anchor_decisions"]["suggested_groups"][0]["file_count"] = file_count
                report["rule_audit"]["rule_effects"][0]["matched_file_count"] = file_count
                risks = {
                    item["risk_level"]
                    for item in build_organization_review(report)["items"]
                }
                self.assertEqual(risks, {expected})

    def test_overwrite_risk_is_always_high(self) -> None:
        report = sample_report()
        report["organization_suggestions"][0]["plan_items"][0]["overwrite_risk"] = True

        item = next(
            item
            for item in build_organization_review(report)["items"]
            if item["source"] == "CS1010X lecture 02.pdf"
        )

        self.assertEqual(item["risk_level"], "high")

    def test_narrow_evidence_is_low_risk(self) -> None:
        report = sample_report()
        decision = report["anchor_decisions"]["suggested_groups"][0]
        decision["evidence"] = "year_variant_set"
        report["rule_audit"]["rule_effects"] = []

        risks = {
            item["risk_level"]
            for item in build_organization_review(report)["items"]
        }

        self.assertEqual(risks, {"low"})

    def test_preferred_granularities_do_not_create_rows(self) -> None:
        report = sample_report()
        report["organization_suggestions"] = []
        report["anchor_decisions"]["suggested_groups"] = []

        data = build_organization_review(report)

        self.assertEqual(data["items"], [])
        self.assertEqual(
            data["rule_audit_summary"]["preferred_granularities"],
            ["course_code"],
        )

    def test_no_rules_still_exports_valid_review(self) -> None:
        report = sample_report()
        report["rule_audit"].update(
            {
                "rules_loaded": False,
                "rules_path": None,
                "locked_anchors": [],
                "preferred_granularities": [],
                "rule_effects": [],
                "warnings": ["No organization rules file found."],
            }
        )
        report["anchor_decisions"]["suggested_groups"][0]["evidence"] = "year_variant_set"

        data = build_organization_review(report)

        self.assertFalse(data["rules_loaded"])
        self.assertIsNone(data["rules_path"])
        self.assertEqual(len(data["items"]), 2)

    def test_loaded_rules_include_locked_anchor_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "AI_Review" / "config" / "organization_rules.json"
            rules_path.parent.mkdir(parents=True)
            rules_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "locked_anchors": ["CS1010X", "EvoSim", "OurDream"],
                    }
                ),
                encoding="utf-8",
            )
            for anchor in ["CS1010X", "EvoSim", "OurDream"]:
                (root / f"{anchor} notes.pdf").write_text("one", encoding="utf-8")
                (root / f"{anchor} slides.pdf").write_text("two", encoding="utf-8")

            data = build_organization_review(build_scan_report(root))

            self.assertTrue(data["rules_loaded"])
            self.assertEqual(
                {item["anchor"] for item in data["items"]},
                {"CS1010X", "EvoSim", "OurDream"},
            )

    def test_empty_suggestions_export_valid_file_with_warning(self) -> None:
        report = sample_report()
        report["organization_suggestions"] = []
        report["anchor_decisions"]["suggested_groups"] = []

        data = build_organization_review(report)

        self.assertEqual(data["items"], [])
        self.assertIn(
            "No organization suggestions were available for review.",
            data["rule_audit_summary"]["warnings"],
        )

    def test_default_output_is_collision_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            first = export_organization_review(sample_report(), root)
            second = export_organization_review(sample_report(), root)

            self.assertEqual(first.name, "organization_review.json")
            self.assertEqual(second.name, "organization_review_1.json")
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_explicit_output_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "AI_Review" / "reviews" / "manual.json"
            output.parent.mkdir(parents=True)
            output.write_text("manual", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "already exists"):
                export_organization_review(sample_report(), root, output)

            self.assertEqual(output.read_text(encoding="utf-8"), "manual")

    def test_explicit_relative_output_is_written_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            output = export_organization_review(
                sample_report(),
                root,
                Path("AI_Review/reviews/manual.json"),
            )

            self.assertEqual(
                output,
                (root / "AI_Review" / "reviews" / "manual.json").resolve(),
            )
            self.assertTrue(output.exists())

    def test_optional_output_must_remain_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)

            with self.assertRaises(ValueError):
                export_organization_review(
                    sample_report(),
                    root,
                    Path(outside) / "review.json",
                )

    def test_optional_output_rejects_symlink_parent_escape(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are not supported")
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            link = root / "linked"
            try:
                link.symlink_to(Path(outside), target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlink creation is not supported: {error}")

            with self.assertRaises(ValueError):
                export_organization_review(
                    sample_report(),
                    root,
                    Path("linked") / "review.json",
                )

    def test_validator_accepts_all_decisions_and_user_notes(self) -> None:
        for decision in ["approve", "reject", "undecided"]:
            with self.subTest(decision=decision):
                data = build_organization_review(sample_report())
                data["items"][0]["decision"] = decision
                data["items"][0]["note"] = "Reviewed manually."

                self.assertIs(validate_organization_review_data(data), data)

    def test_validator_allows_nonexistent_organized_destination(self) -> None:
        data = build_organization_review(sample_report())
        data["items"][0]["destination"] = "Organized/New_Group/notes/future.pdf"

        validate_organization_review_data(data)

    def test_validator_rejects_malformed_top_level_data(self) -> None:
        data = build_organization_review(sample_report())
        del data["schema_version"]
        with self.assertRaisesRegex(ValueError, "missing field"):
            validate_organization_review_data(data)

        data = build_organization_review(sample_report())
        data["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "schema_version"):
            validate_organization_review_data(data)

        data = build_organization_review(sample_report())
        del data["items"]
        with self.assertRaisesRegex(ValueError, "items"):
            validate_organization_review_data(data)

        with self.assertRaisesRegex(ValueError, "JSON object"):
            validate_organization_review_data([])

    def test_validator_rejects_invalid_item_edits(self) -> None:
        cases = {
            "duplicate id": lambda data: data["items"].__setitem__(
                1,
                {**data["items"][1], "review_id": data["items"][0]["review_id"]},
            ),
            "invalid id": lambda data: data["items"][0].__setitem__("review_id", "O1"),
            "invalid decision": lambda data: data["items"][0].__setitem__("decision", "accept"),
            "absolute source": lambda data: data["items"][0].__setitem__("source", "/tmp/a.pdf"),
            "windows absolute source": lambda data: data["items"][0].__setitem__("source", "C:/tmp/a.pdf"),
            "traversal source": lambda data: data["items"][0].__setitem__("source", "../a.pdf"),
            "absolute destination": lambda data: data["items"][0].__setitem__("destination", "/tmp/a.pdf"),
            "traversal destination": lambda data: data["items"][0].__setitem__("destination", "Organized/../a.pdf"),
            "wrong namespace": lambda data: data["items"][0].__setitem__("destination", "AI_Review/a.pdf"),
            "path anchor": lambda data: data["items"][0].__setitem__("anchor", "course/name"),
            "windows path anchor": lambda data: data["items"][0].__setitem__("anchor", "C:course"),
            "low confidence": lambda data: data["items"][0].__setitem__("confidence", -1),
            "high confidence": lambda data: data["items"][0].__setitem__("confidence", 101),
            "unknown risk": lambda data: data["items"][0].__setitem__("risk_level", "extreme"),
            "nonboolean overwrite": lambda data: data["items"][0].__setitem__("overwrite_risk", 0),
            "malformed note": lambda data: data["items"][0].__setitem__("note", []),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                data = deepcopy(build_organization_review(sample_report()))
                mutate(data)
                with self.assertRaises(ValueError):
                    validate_organization_review_data(data)

    def test_load_validates_user_edited_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = export_organization_review(sample_report(), root)
            data = json.loads(output.read_text(encoding="utf-8"))
            data["items"][0]["decision"] = "approve"
            data["items"][0]["note"] = "Reviewed."
            output.write_text(json.dumps(data), encoding="utf-8")

            loaded = load_organization_review(output, root)

            self.assertEqual(loaded["items"][0]["decision"], "approve")
            self.assertEqual(loaded["items"][0]["note"], "Reviewed.")

    def test_export_changes_only_review_output_area(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "CS1010X lecture 01.pdf"
            source.write_text("content", encoding="utf-8")

            export_organization_review(sample_report(), root)

            self.assertEqual(source.read_text(encoding="utf-8"), "content")
            self.assertFalse((root / "Organized").exists())
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())
            self.assertFalse(
                (root / "AI_Review" / "config" / "organization_rules.json").exists()
            )

    def test_cli_exports_review_and_allows_max_depth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CS1010X finals 2025.pdf").write_text("one", encoding="utf-8")
            (root / "CS1010X finals 2026.pdf").write_text("two", encoding="utf-8")

            result = run_cli(root, "--export-organization-review", "--max-depth", "1")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Organization review exported:", result.stdout)
            self.assertIn("Decisions default to undecided", result.stdout)
            output = root / "AI_Review" / "reviews" / "organization_review.json"
            self.assertTrue(output.exists())
            self.assertFalse((root / "Organized").exists())

    def test_cli_export_is_single_purpose(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for incompatible in [
                ("--duplicates",),
                ("--report",),
                ("--plan-organization",),
                ("--apply-organization-plan",),
                ("--undo-log", "log.json"),
                ("--export-rule-candidates",),
                ("--refine-groups", "--llm-provider", "ollama", "--llm-model", "x"),
                ("--ollama-host", "http://localhost:11434"),
                ("--confirm", "ANYTHING"),
            ]:
                with self.subTest(incompatible=incompatible):
                    result = run_cli(root, "--export-organization-review", *incompatible)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("may be combined only with --max-depth", result.stderr)

    def test_output_flag_requires_export_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(
                Path(directory),
                "--organization-review-output",
                "review.json",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires --export-organization-review", result.stderr)

    def test_module_has_no_movement_dependency(self) -> None:
        module_path = Path(__file__).resolve().parents[1] / "src" / "organizer" / "organization_review.py"
        source = module_path.read_text(encoding="utf-8")

        self.assertNotIn("exec" + "utor", source)
        self.assertNotIn("Move" + "PlanItem", source)

    def test_documentation_sample_and_schema_are_valid_json(self) -> None:
        docs = Path(__file__).resolve().parents[1] / "docs"
        sample = json.loads(
            (docs / "examples" / "sample_organization_review.json").read_text(
                encoding="utf-8"
            )
        )
        schema = json.loads(
            (docs / "schemas" / "organization_review.schema.json").read_text(
                encoding="utf-8"
            )
        )

        validate_organization_review_data(sample)
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)


def sample_report() -> dict[str, object]:
    return {
        "scan_root": ".",
        "anchor_decisions": {
            "suggested_groups": [
                {
                    "anchor": "CS1010X",
                    "decision": "suggested",
                    "evidence": "locked_anchor",
                    "file_count": 2,
                    "reason": "files share locked anchor CS1010X",
                    "examples": [
                        "CS1010X lecture 01.pdf",
                        "CS1010X lecture 02.pdf",
                    ],
                }
            ],
            "needs_decision": [],
            "ignored_terms": [],
        },
        "organization_suggestions": [
            {
                "group_name": "CS1010X",
                "suggested_root": "Organized/CS1010X",
                "plan_items": [
                    {
                        "source": "CS1010X lecture 02.pdf",
                        "destination": "Organized/CS1010X/lectures/CS1010X lecture 02.pdf",
                        "reason": "files share locked anchor CS1010X; suggested subfolder lectures",
                        "confidence": 80,
                        "operation": "dry-run move",
                        "overwrite_risk": False,
                    },
                    {
                        "source": "CS1010X lecture 01.pdf",
                        "destination": "Organized/CS1010X/lectures/CS1010X lecture 01.pdf",
                        "reason": "files share locked anchor CS1010X; suggested subfolder lectures",
                        "confidence": 80,
                        "operation": "dry-run move",
                        "overwrite_risk": False,
                    },
                ],
            }
        ],
        "rule_audit": {
            "rules_loaded": True,
            "rules_path": "AI_Review/config/organization_rules.json",
            "locked_anchors": ["CS1010X"],
            "ignored_terms": [],
            "anchor_aliases": {},
            "preferred_granularities": ["course_code"],
            "before_after_counts": {},
            "rule_effects": [
                {
                    "rule_type": "locked_anchor",
                    "value": "CS1010X",
                    "effect": "rule applied",
                    "matched_file_count": 2,
                    "affected_anchors": ["CS1010X"],
                    "before_decision": "needs_decision",
                    "after_decision": "locked_anchor",
                    "risk_level": "low",
                    "warning": "",
                }
            ],
            "warnings": [],
        },
    }


def run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source_root = Path(__file__).resolve().parents[1] / "src"
    environment["PYTHONPATH"] = str(source_root)
    return subprocess.run(
        [sys.executable, "-m", "organizer.cli", str(root), *arguments],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()
