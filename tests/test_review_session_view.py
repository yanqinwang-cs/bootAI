from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from organizer.models import MovePlanItem, ReviewedPlanItem
from organizer.review_session import (
    DEFAULT_REVIEW_PAGE_SIZE,
    MAX_REVIEW_PAGE_SIZE,
    ReviewViewState,
    apply_review_filters,
    build_review_view,
    clear_review_filters,
    clear_review_sort,
    set_review_filter,
    set_review_page,
    set_review_page_size,
    set_review_sort,
    sort_review_rows,
)


class ReviewViewFilterTests(unittest.TestCase):
    def test_filters_combine_replace_clear_and_do_not_change_decisions(self) -> None:
        root = Path("/tmp/review-root")
        items = make_items(root)
        original_decisions = [item.decision for item in items]
        state = set_review_filter(ReviewViewState(), "decision", "approved")
        state = set_review_filter(state, "category", "organization")

        filtered = apply_review_filters(items, state)
        replaced = set_review_filter(state, "decision", "rejected")
        cleared = clear_review_filters(replaced)

        self.assertEqual([item.id for item in filtered], ["O001"])
        self.assertEqual(
            [item.id for item in apply_review_filters(items, replaced)],
            ["O002"],
        )
        self.assertEqual(apply_review_filters(items, cleared), items)
        self.assertEqual([item.decision for item in items], original_decisions)
        self.assertEqual(state.page, 1)

    def test_review_category_and_zero_match_filters(self) -> None:
        root = Path("/tmp/review-root")
        items = make_items(root)
        temporary = set_review_filter(
            ReviewViewState(),
            "review_category",
            "temporary",
        )
        no_match = set_review_filter(
            temporary,
            "decision",
            "rejected",
        )

        self.assertEqual(
            [item.id for item in apply_review_filters(items, temporary)],
            ["R001"],
        )
        view = build_review_view(items, no_match, root)
        self.assertEqual(view.rows, [])
        self.assertEqual((view.page, view.total_pages), (0, 0))

    def test_invalid_filter_field_and_value_leave_state_unchanged(self) -> None:
        state = ReviewViewState()
        for field, value in (("risk", "high"), ("decision", "maybe")):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                set_review_filter(state, field, value)
        self.assertEqual(state, ReviewViewState())


class ReviewViewSortTests(unittest.TestCase):
    def test_sort_ascending_descending_default_and_clear(self) -> None:
        root = Path("/tmp/review-root")
        items = make_items(root)
        ascending = set_review_sort(ReviewViewState(page=2), "source")
        descending = set_review_sort(ascending, "source", "desc")

        self.assertEqual(ascending.sort_direction, "asc")
        self.assertEqual(ascending.page, 1)
        self.assertEqual(
            [item.plan_item.source.name for item in sort_review_rows(items, ascending, root)],
            ["a.txt", "b.txt", "c.txt", "same.txt", "same.txt"],
        )
        self.assertEqual(
            sort_review_rows(items, descending, root)[0].plan_item.source.name,
            "same.txt",
        )
        self.assertEqual(clear_review_sort(descending), ReviewViewState())

    def test_sort_ties_use_stable_id_order(self) -> None:
        root = Path("/tmp/review-root")
        items = make_items(root)
        state = set_review_sort(ReviewViewState(), "source", "desc")

        same_source_ids = [
            item.id
            for item in sort_review_rows(items, state, root)
            if item.plan_item.source.name == "same.txt"
        ]

        self.assertEqual(same_source_ids, ["D001", "D002"])

    def test_invalid_sort_field_and_direction_are_rejected(self) -> None:
        state = ReviewViewState()
        with self.assertRaises(ValueError):
            set_review_sort(state, "size")
        with self.assertRaises(ValueError):
            set_review_sort(state, "source", "sideways")
        self.assertEqual(state, ReviewViewState())


class ReviewViewPaginationTests(unittest.TestCase):
    def test_default_first_next_previous_direct_and_partial_pages(self) -> None:
        root = Path("/tmp/review-root")
        items = make_many_items(root, 27)
        state = ReviewViewState()
        first = build_review_view(items, state, root)
        next_state = set_review_page(state, "next", items, root)
        last = build_review_view(items, next_state, root)
        previous = set_review_page(next_state, "prev", items, root)
        direct = set_review_page(state, "2", items, root)

        self.assertEqual(DEFAULT_REVIEW_PAGE_SIZE, 25)
        self.assertEqual((first.page, first.total_pages, len(first.rows)), (1, 2, 25))
        self.assertEqual((last.page, len(last.rows)), (2, 2))
        self.assertEqual(previous.page, 1)
        self.assertEqual(direct.page, 2)

    def test_invalid_page_navigation_does_not_wrap(self) -> None:
        root = Path("/tmp/review-root")
        items = make_many_items(root, 3)
        state = ReviewViewState(page_size=2)
        invalid_requests = ["prev", "0", "-1", "3", "not-a-page"]
        for request in invalid_requests:
            with self.subTest(request=request), self.assertRaises(ValueError):
                set_review_page(state, request, items, root)
        final = set_review_page(state, "2", items, root)
        with self.assertRaises(ValueError):
            set_review_page(final, "next", items, root)

    def test_page_size_validation_and_view_resets(self) -> None:
        state = ReviewViewState(page=4)
        resized = set_review_page_size(state, "10")
        self.assertEqual((resized.page_size, resized.page), (10, 1))
        for value in ("0", "-1", "not-int", str(MAX_REVIEW_PAGE_SIZE + 1)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                set_review_page_size(state, value)
        self.assertEqual(set_review_filter(state, "decision", "approved").page, 1)
        self.assertEqual(set_review_sort(state, "source").page, 1)

    def test_zero_row_view_has_page_zero_of_zero(self) -> None:
        root = Path("/tmp/review-root")
        items = make_items(root)
        state = set_review_filter(ReviewViewState(), "decision", "undecided")
        state = set_review_filter(state, "category", "duplicate")
        view = build_review_view(items, state, root)

        self.assertEqual((view.page, view.total_pages), (0, 0))
        with self.assertRaises(ValueError):
            set_review_page(state, "next", items, root)


class ReviewViewCliTests(unittest.TestCase):
    def test_resumed_session_view_show_hidden_details_and_stable_id_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text=(
                    "page-size 1\n"
                    "filter category organization\n"
                    "sort source desc\n"
                    "view\n"
                    "show\n"
                    "details D001\n"
                    "reject D001\n"
                    "clear-sort\n"
                    "clear-filter\n"
                    "view\n"
                    "quit\n"
                ),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("filters: category=organization", result.stdout)
            self.assertIn("sort: source desc", result.stdout)
            self.assertIn("matching rows: 2", result.stdout)
            self.assertIn("total session rows: 5", result.stdout)
            self.assertIn("D001", result.stdout)
            self.assertIn("Rejected 1 reviewed plan item", result.stdout)
            self.assertFalse(plan.with_name("reviewed_plan_1.json").exists())
            self.assertFalse((root / "AI_Review" / "operation_logs").exists())

    def test_filtered_save_keeps_every_row_and_omits_view_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text="filter decision approved\npage-size 1\nsave\nquit\n",
            )
            saved = plan.with_name("reviewed_plan_1.json")
            data = read_json(saved)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(data["items"]), 5)
            self.assertNotIn("filters", data)
            self.assertNotIn("page_size", data)
            self.assertEqual(
                [item["id"] for item in data["items"]],
                ["D001", "D002", "O001", "O002", "R001"],
            )

    def test_new_review_session_supports_view_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            (root / "b.txt").write_text("same", encoding="utf-8")

            result = run_cli(
                root,
                "--review-plans",
                input_text="filter category duplicate\nview\nshow\nquit\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("filters: category=duplicate", result.stdout)
            self.assertIn("matching rows: 1", result.stdout)
            self.assertIn("D1", result.stdout)

    def test_invalid_view_commands_do_not_change_decisions_or_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = write_reviewed_plan(root)
            original = plan.read_text(encoding="utf-8")
            result = run_cli(
                root,
                "--resume-reviewed-plan",
                str(plan),
                input_text=(
                    "filter risk high\n"
                    "sort size desc\n"
                    "page 0\n"
                    "page-size 0\n"
                    "filter\n"
                    "sort\n"
                    "page\n"
                    "page-size\n"
                    "quit\n"
                ),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreaterEqual(result.stdout.count("Error:"), 8)
            self.assertEqual(plan.read_text(encoding="utf-8"), original)
            self.assertFalse(plan.with_name("reviewed_plan_1.json").exists())


def make_items(root: Path) -> list[ReviewedPlanItem]:
    return [
        make_item(root, "D002", "duplicate", "same.txt", "approved"),
        make_item(root, "D001", "duplicate", "same.txt", "approved"),
        make_item(root, "O002", "organization", "c.txt", "rejected"),
        make_item(root, "O001", "organization", "a.txt", "approved"),
        make_item(
            root,
            "R001",
            "review_candidate",
            "b.txt",
            "undecided",
            review_category="temporary",
        ),
    ]


def make_many_items(root: Path, count: int) -> list[ReviewedPlanItem]:
    return [
        make_item(root, f"D{index:03d}", "duplicate", f"file-{index:03d}.txt", "approved")
        for index in range(1, count + 1)
    ]


def make_item(
    root: Path,
    item_id: str,
    category: str,
    source: str,
    decision: str,
    *,
    review_category: str | None = None,
) -> ReviewedPlanItem:
    return ReviewedPlanItem(
        id=item_id,
        category=category,
        decision=decision,
        review_category=review_category,
        plan_item=MovePlanItem(
            source=root / source,
            destination=root / "AI_Review" / category / source,
            reason="test review row",
            confidence=100,
            operation="dry-run move",
            overwrite_risk=False,
        ),
    )


def write_reviewed_plan(root: Path) -> Path:
    items = make_items(root)
    path = root / "AI_Review" / "review_sessions" / "reviewed_plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "created_at": "2026-07-10T12:00:00+00:00",
        "scan_root": ".",
        "plan_type": "batch_review",
        "summary": {},
        "items": [
            {
                "id": item.id,
                "category": item.category,
                "decision": item.decision,
                "source": item.plan_item.source.relative_to(root).as_posix(),
                "destination": item.plan_item.destination.relative_to(root).as_posix(),
                "reason": item.plan_item.reason,
                "confidence": item.plan_item.confidence,
                "operation": item.plan_item.operation,
                "overwrite_risk": item.plan_item.overwrite_risk,
                **(
                    {"review_category": item.review_category}
                    if item.review_category is not None
                    else {}
                ),
            }
            for item in sorted(items, key=lambda row: row.id)
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    assert isinstance(data, dict)
    return data


def run_cli(
    root: Path,
    *args: str,
    input_text: str = "",
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, "-m", "organizer.cli", str(root), *args],
        input=input_text,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()
