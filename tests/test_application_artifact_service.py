import json
import os
from pathlib import Path
import tempfile
import unittest

from organizer.application.artifact_service import (
    ARTIFACT_REVIEWED_PLAN,
    ARTIFACT_SCAN_REPORT,
    InvalidArtifact,
    UnsupportedArtifact,
    list_artifacts,
    load_artifact,
)
from organizer.application.review_service import create_review_session
from organizer.reports import build_scan_report, load_report, write_report
from organizer.review_session import save_reviewed_plan


class ArtifactServiceTests(unittest.TestCase):
    def test_lists_only_allowlisted_artifacts_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            report_path = write_report(
                build_scan_report(root),
                root,
                Path("AI_Review/reports/z.json"),
            )
            session = create_review_session(root)
            reviewed_path = save_reviewed_plan(list(session.items), root)
            unrelated = root / "notes.json"
            unrelated.write_text("{}", encoding="utf-8")
            future = root / "AI_Review" / "operation_logs" / "operation_log.json"
            future.parent.mkdir(parents=True)
            future.write_text('{"operations": []}', encoding="utf-8")

            summaries = list_artifacts(root)

            self.assertEqual(
                tuple((item.artifact_type, item.relative_path) for item in summaries),
                (
                    (ARTIFACT_REVIEWED_PLAN, reviewed_path.relative_to(root).as_posix()),
                    (ARTIFACT_SCAN_REPORT, report_path.relative_to(root).as_posix()),
                ),
            )

    def test_loads_report_and_reviewed_plan_through_existing_owners(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            report = build_scan_report(root)
            report_path = write_report(report, root)
            session = create_review_session(root)
            reviewed_path = save_reviewed_plan(list(session.items), root)

            loaded_report = load_artifact(
                root,
                ARTIFACT_SCAN_REPORT,
                report_path.relative_to(root),
            )
            loaded_plan = load_artifact(
                root,
                ARTIFACT_REVIEWED_PLAN,
                reviewed_path.relative_to(root),
            )

            self.assertEqual(loaded_report.payload, report)
            self.assertEqual(loaded_plan.payload, session.items)
            self.assertEqual(loaded_report.summary.relative_path, report_path.relative_to(root).as_posix())
            self.assertEqual(loaded_plan.summary.relative_path, reviewed_path.relative_to(root).as_posix())

    def test_report_owner_rejects_malformed_or_wrong_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            reports = root / "AI_Review" / "reports"
            reports.mkdir(parents=True)
            malformed = reports / "malformed.json"
            malformed.write_text("{bad json", encoding="utf-8")
            wrong = reports / "wrong.json"
            wrong.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")

            with self.assertRaisesRegex(InvalidArtifact, "invalid report JSON"):
                load_artifact(root, ARTIFACT_SCAN_REPORT, malformed.relative_to(root))
            with self.assertRaisesRegex(InvalidArtifact, "fields do not match"):
                load_artifact(root, ARTIFACT_SCAN_REPORT, wrong.relative_to(root))
            with self.assertRaises(ValueError):
                load_report(wrong, root)

    def test_reviewed_plan_owner_rejects_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "AI_Review" / "review_sessions" / "bad.json"
            path.parent.mkdir(parents=True)
            path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(InvalidArtifact, "JSON object"):
                load_artifact(root, ARTIFACT_REVIEWED_PLAN, path.relative_to(root))

    def test_rejects_unsupported_missing_and_non_json_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaises(UnsupportedArtifact):
                list_artifacts(root, "operation_log")
            with self.assertRaises(UnsupportedArtifact):
                load_artifact(root, "organization_review", "AI_Review/reviews/a.json")
            with self.assertRaisesRegex(InvalidArtifact, "does not exist"):
                load_artifact(
                    root,
                    ARTIFACT_SCAN_REPORT,
                    "AI_Review/reports/missing.json",
                )

            text = root / "AI_Review" / "reports" / "report.txt"
            text.parent.mkdir(parents=True)
            text.write_text("text", encoding="utf-8")
            with self.assertRaisesRegex(InvalidArtifact, "JSON file"):
                load_artifact(root, ARTIFACT_SCAN_REPORT, text.relative_to(root))

    def test_rejects_arbitrary_outside_traversal_and_wrong_allowlist_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside_directory:
            root = Path(directory).resolve()
            outside = Path(outside_directory) / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            unrelated = root / "notes.json"
            unrelated.write_text("{}", encoding="utf-8")

            for unsafe in (outside, Path("../outside.json"), Path("notes.json")):
                with self.subTest(path=unsafe):
                    with self.assertRaises(InvalidArtifact):
                        load_artifact(root, ARTIFACT_SCAN_REPORT, unsafe)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are not supported")
    def test_rejects_direct_symlink_and_does_not_list_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            report_path = write_report(build_scan_report(root), root)
            link = report_path.with_name("linked.json")
            link.symlink_to(report_path)

            summaries = list_artifacts(root, ARTIFACT_SCAN_REPORT)
            self.assertNotIn(link.relative_to(root).as_posix(), [item.relative_path for item in summaries])
            with self.assertRaisesRegex(InvalidArtifact, "symlink"):
                load_artifact(root, ARTIFACT_SCAN_REPORT, link.relative_to(root))


if __name__ == "__main__":
    unittest.main()
