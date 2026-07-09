from pathlib import Path
import tempfile
import unittest

from organizer.grouping import analyze_anchor_decisions
from organizer.pattern_inference import (
    PATTERN_COURSE_CODE_FOLDERING,
    PATTERN_PERSON_OR_STUDENT_FOLDERING,
    PATTERN_PROJECT_FOLDERING,
    PATTERN_ROLE_FOLDERING,
    RULE_PREFERRED_GRANULARITY_CANDIDATE,
    infer_organization_patterns,
    pattern_evidence_for_anchor,
)
from organizer.reports import build_scan_report
from organizer.scanner import scan_directory


class PatternInferenceTests(unittest.TestCase):
    def test_course_code_foldering_does_not_prioritize_unrelated_loose_course_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / "CS1010X"
            course.mkdir()
            (course / "CS1010X finals.pdf").write_text("x", encoding="utf-8")
            (course / "CS1010X recitation 01.pdf").write_text("x", encoding="utf-8")
            (root / "CS2020 finals.pdf").write_text("x", encoding="utf-8")
            (root / "CS2020 recitation 01.pdf").write_text("x", encoding="utf-8")

            metadata = scan_directory(root)
            decisions = analyze_anchor_decisions(metadata)
            inference = infer_organization_patterns(metadata, decisions)

            self.assertIn(PATTERN_COURSE_CODE_FOLDERING, {pattern.pattern_type for pattern in inference.patterns})
            self.assertIn(
                RULE_PREFERRED_GRANULARITY_CANDIDATE,
                {candidate.rule_type for candidate in inference.rule_candidates},
            )
            self.assertIsNone(pattern_evidence_for_anchor("CS2020", inference))
            self.assertFalse((root / "AI_Review" / "config" / "organization_rules.json").exists())
            self.assertFalse(hasattr(inference, "plan_items"))

    def test_compound_course_folders_create_report_only_pattern_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            finals = root / "cs1010x finals"
            finals.mkdir()
            (finals / "cs1010x-final-jun21.pdf").write_text("x", encoding="utf-8")
            (finals / "cs1010x-final-solutions-jun21.pdf").write_text("x", encoding="utf-8")
            pe = root / "CS1010x PE"
            pe.mkdir()
            (pe / "2021 PE qns.pdf").write_text("x", encoding="utf-8")
            (pe / "2022 PE qns.pdf").write_text("x", encoding="utf-8")
            renamed = root / "CS1010X_renamed"
            renamed.mkdir()
            (renamed / "renamed notes.pdf").write_text("x", encoding="utf-8")
            (renamed / "renamed slides.pptx").write_text("x", encoding="utf-8")
            tutorials = root / "MA2001 tutorials"
            tutorials.mkdir()
            (tutorials / "MA2001 tutorial 01.pdf").write_text("x", encoding="utf-8")
            (tutorials / "MA2001 tutorial 02.pdf").write_text("x", encoding="utf-8")

            report = build_scan_report(root)
            needs_decision = report["anchor_decisions"]["needs_decision"]

            self.assertGreater(report["summary"]["organization_pattern_count"], 0)
            self.assertGreater(report["summary"]["inferred_rule_candidate_count"], 0)
            self.assertIn(
                PATTERN_COURSE_CODE_FOLDERING,
                {
                    pattern["pattern_type"]
                    for pattern in report["organization_pattern_inference"]["patterns"]
                },
            )
            self.assertIn(
                PATTERN_ROLE_FOLDERING,
                {
                    pattern["pattern_type"]
                    for pattern in report["organization_pattern_inference"]["patterns"]
                },
            )
            cs1010x = next(item for item in needs_decision if item["anchor"] == "CS1010X")
            self.assertEqual(cs1010x["pattern_evidence"]["priority"], "high")
            for noisy_anchor in ["Jun21", "Solutions", "2021", "2022", "Qns"]:
                decision = next((item for item in needs_decision if item["anchor"] == noisy_anchor), None)
                if decision is not None:
                    self.assertNotIn("pattern_evidence", decision)
            self.assertFalse((root / "AI_Review" / "config" / "organization_rules.json").exists())

    def test_project_foldering_does_not_mark_unrelated_loose_project_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "EvoSim"
            project.mkdir()
            (project / "EvoSim project slides.pptx").write_text("x", encoding="utf-8")
            (project / "EvoSim report.pdf").write_text("x", encoding="utf-8")
            (root / "NewProjectX notes.pdf").write_text("x", encoding="utf-8")
            (root / "NewProjectX slides.pptx").write_text("x", encoding="utf-8")

            metadata = scan_directory(root)
            inference = infer_organization_patterns(metadata, analyze_anchor_decisions(metadata))

            self.assertIn(PATTERN_PROJECT_FOLDERING, {pattern.pattern_type for pattern in inference.patterns})
            self.assertIsNone(pattern_evidence_for_anchor("NewProjectX", inference))

    def test_compound_and_lowercase_project_folders_create_pattern_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evosim = root / "EvoSim images"
            evosim.mkdir()
            (evosim / "EvoSim_project_slides.pptx").write_text("x", encoding="utf-8")
            (evosim / "EvoSim_fixed_google_slides.pptx").write_text("x", encoding="utf-8")
            ourdream = root / "ourdream"
            ourdream.mkdir()
            (ourdream / "OurDream_Character_Guide.pdf").write_text("x", encoding="utf-8")
            (ourdream / "OurDream_Image_Generation_Rules_v2.md").write_text("x", encoding="utf-8")
            elarian = root / "Elarian_Realms drafts"
            elarian.mkdir()
            (elarian / "Elarian_Realms_outline.pdf").write_text("x", encoding="utf-8")
            (elarian / "Elarian_Realms_notes.md").write_text("x", encoding="utf-8")

            report = build_scan_report(root)
            needs_decision = report["anchor_decisions"]["needs_decision"]

            self.assertIn(
                PATTERN_PROJECT_FOLDERING,
                {
                    pattern["pattern_type"]
                    for pattern in report["organization_pattern_inference"]["patterns"]
                },
            )
            evosim_decision = next(item for item in needs_decision if item["anchor"] == "EvoSim")
            ourdream_decision = next(item for item in needs_decision if item["anchor"] == "OurDream")
            self.assertIn(evosim_decision["pattern_evidence"]["priority"], {"high", "medium"})
            self.assertIn(ourdream_decision["pattern_evidence"]["priority"], {"high", "medium"})
            for noisy_anchor in ["Google", "Fixed", "Character", "Generation", "Rules"]:
                decision = next((item for item in needs_decision if item["anchor"] == noisy_anchor), None)
                if decision is not None:
                    self.assertNotIn("pattern_evidence", decision)
            self.assertFalse((root / "AI_Review" / "config" / "organization_rules.json").exists())

    def test_lowercase_project_folder_can_support_existing_broad_anchor_without_filename_repetition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ourdream = root / "ourdream"
            ourdream.mkdir()
            (ourdream / "Harem pre-release.rtf").write_text("x", encoding="utf-8")
            (ourdream / "Custom_Instructions_HUD_MD v4.md").write_text("x", encoding="utf-8")
            (root / "OurDream notes.pdf").write_text("x", encoding="utf-8")
            (root / "OurDream slides.pptx").write_text("x", encoding="utf-8")

            report = build_scan_report(root)
            needs_decision = report["anchor_decisions"]["needs_decision"]
            ourdream_decision = next(item for item in needs_decision if item["anchor"] == "OurDream")

            self.assertEqual(
                ourdream_decision["pattern_evidence"]["matched_patterns"],
                [PATTERN_PROJECT_FOLDERING],
            )
            for noisy_anchor in ["Harem", "Custom_Instructions", "HUD", "MD"]:
                decision = next((item for item in needs_decision if item["anchor"] == noisy_anchor), None)
                if decision is not None:
                    self.assertNotIn("pattern_evidence", decision)

    def test_person_foldering_uses_sibling_structure_without_repeated_file_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["Wang", "Tan", "Aisha"]:
                folder = root / "Submissions" / name
                folder.mkdir(parents=True)
                (folder / "assignment 1.pdf").write_text("x", encoding="utf-8")
                (folder / "assignment 2.pdf").write_text("x", encoding="utf-8")

            metadata = scan_directory(root)
            inference = infer_organization_patterns(metadata, analyze_anchor_decisions(metadata))

            self.assertIn(PATTERN_PERSON_OR_STUDENT_FOLDERING, {pattern.pattern_type for pattern in inference.patterns})
            self.assertEqual(pattern_evidence_for_anchor("Aisha", inference)["priority"], "high")

    def test_role_foldering_detects_existing_role_folders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lectures = root / "lectures"
            lectures.mkdir()
            (lectures / "CS1010X lecture 01.pdf").write_text("x", encoding="utf-8")
            (lectures / "CS1010X lecture 02.pdf").write_text("x", encoding="utf-8")
            (root / "CS2020 lecture 01.pdf").write_text("x", encoding="utf-8")
            (root / "CS2020 lecture 02.pdf").write_text("x", encoding="utf-8")

            metadata = scan_directory(root)
            inference = infer_organization_patterns(metadata, analyze_anchor_decisions(metadata))

            self.assertIn(PATTERN_ROLE_FOLDERING, {pattern.pattern_type for pattern in inference.patterns})
            self.assertTrue(
                any(candidate.value == "document_role" for candidate in inference.rule_candidates)
            )

    def test_role_foldering_does_not_attach_internal_topic_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lectures = root / "lectures"
            lectures.mkdir()
            (lectures / "CS1010X Object Oriented Programming.pdf").write_text("x", encoding="utf-8")
            (lectures / "CS1010X Java Introduction.pdf").write_text("x", encoding="utf-8")

            report = build_scan_report(root)
            needs_decision = report["anchor_decisions"]["needs_decision"]

            self.assertIn(
                PATTERN_ROLE_FOLDERING,
                {
                    pattern["pattern_type"]
                    for pattern in report["organization_pattern_inference"]["patterns"]
                },
            )
            for noisy_anchor in ["Object", "Oriented", "Programming", "Java"]:
                decision = next((item for item in needs_decision if item["anchor"] == noisy_anchor), None)
                if decision is not None:
                    self.assertNotIn("pattern_evidence", decision)

    def test_person_foldering_does_not_attach_assignment_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["Wang", "Tan", "Aisha"]:
                folder = root / "Submissions" / name
                folder.mkdir(parents=True)
                (folder / "assignment 1.pdf").write_text("x", encoding="utf-8")
                (folder / "assignment 2.pdf").write_text("x", encoding="utf-8")

            metadata = scan_directory(root)
            inference = infer_organization_patterns(metadata, analyze_anchor_decisions(metadata))

            for name in ["Wang", "Tan", "Aisha"]:
                self.assertEqual(pattern_evidence_for_anchor(name, inference)["priority"], "high")
            self.assertIsNone(pattern_evidence_for_anchor("Assignment", inference))

    def test_noisy_project_filenames_do_not_create_rule_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "EvoSim images"
            folder.mkdir()
            (folder / "EvoSim_fixed_google_slides_v1_final_copy.pdf").write_text("x", encoding="utf-8")
            (folder / "EvoSim_presentation_patch_v16_combined.pdf").write_text("x", encoding="utf-8")
            (folder / "EvoSim_object_programming_notes.pdf").write_text("x", encoding="utf-8")

            report = build_scan_report(root)
            candidates = report["organization_pattern_inference"]["rule_candidates"]
            candidate_values = {candidate["value"] for candidate in candidates}

            self.assertIn("EvoSim", candidate_values)
            for noisy_value in ["Google", "Fixed", "V16", "Combined", "Object", "Programming", "Copy"]:
                self.assertNotIn(noisy_value, candidate_values)
            self.assertLessEqual(len(candidates), 3)

    def test_protected_generated_and_tool_owned_contexts_are_not_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AI_Review" / "reports").mkdir(parents=True)
            (root / "AI_Review" / "reports" / "report.pdf").write_text("x", encoding="utf-8")
            (root / "Instagram_files").mkdir()
            (root / "Instagram_files" / "CS1010X finals.pdf").write_text("x", encoding="utf-8")
            (root / "Package.app" / "Contents" / "Resources").mkdir(parents=True)
            (root / "Package.app" / "Contents" / "Resources" / "CS1010X notes.pdf").write_text("x", encoding="utf-8")
            (root / "project" / ".venv" / "lib").mkdir(parents=True)
            (root / "project" / ".venv" / "lib" / "CS1010X lecture.pdf").write_text("x", encoding="utf-8")
            course = root / "CS1010X"
            course.mkdir()
            (course / "CS1010X finals.pdf").write_text("x", encoding="utf-8")
            (course / "CS1010X recitation 01.pdf").write_text("x", encoding="utf-8")

            metadata = scan_directory(root)
            inference = infer_organization_patterns(metadata, analyze_anchor_decisions(metadata))
            examples = {
                example
                for pattern in inference.patterns
                for example in pattern.examples
            }

            self.assertIn("CS1010X/CS1010X finals.pdf", examples)
            self.assertFalse(any(example.startswith("AI_Review/") for example in examples))
            self.assertFalse(any(example.startswith("Instagram_files/") for example in examples))
            self.assertFalse(any(".app/" in example for example in examples))
            self.assertFalse(any(".venv/" in example for example in examples))

    def test_report_generation_does_not_create_rules_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / "CS1010X"
            course.mkdir()
            (course / "CS1010X finals.pdf").write_text("x", encoding="utf-8")
            (course / "CS1010X recitation 01.pdf").write_text("x", encoding="utf-8")

            report = build_scan_report(root)

            self.assertIn("organization_pattern_inference", report)
            self.assertFalse((root / "AI_Review" / "config" / "organization_rules.json").exists())


if __name__ == "__main__":
    unittest.main()
