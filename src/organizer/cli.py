import argparse
from pathlib import Path

from organizer.duplicates import find_exact_duplicates
from organizer.executor import apply_move_plan, undo_operation_log
from organizer.models import MovePlanItem, OperationLog
from organizer.planner import build_duplicate_review_plan
from organizer.review import build_review_candidate_plan, detect_review_candidates
from organizer.scanner import scan_directory

CONFIRM_APPLY_DUPLICATE_PLAN = "APPLY_DUPLICATE_PLAN"


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a read-only file metadata report.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--duplicates", action="store_true")
    parser.add_argument("--plan-duplicates", action="store_true")
    parser.add_argument("--apply-duplicate-plan", action="store_true")
    parser.add_argument("--confirm", default=None)
    parser.add_argument("--undo-log", type=Path, default=None)
    parser.add_argument("--review-candidates", action="store_true")
    parser.add_argument("--plan-review-candidates", action="store_true")
    args = parser.parse_args()

    if args.undo_log is not None:
        if (
            args.duplicates
            or args.plan_duplicates
            or args.apply_duplicate_plan
            or args.confirm is not None
            or args.review_candidates
            or args.plan_review_candidates
        ):
            parser.error("--undo-log cannot be combined with planning or review flags")
        operation_log = undo_operation_log(args.undo_log, args.folder)
        print("Undo operation results")
        _print_operation_log(operation_log)
        return

    metadata_items = scan_directory(args.folder, max_depth=args.max_depth)
    print(f"Metadata report for {args.folder.resolve()}")
    print(f"Items: {len(metadata_items)}")

    for metadata in metadata_items:
        item_type = "dir " if metadata.is_dir else "file"
        print(
            f"- {metadata.relative_path.as_posix() or '.'} "
            f"[{item_type}] size={metadata.size_bytes} bytes "
            f"modified={metadata.modified_time:.0f}"
        )

    duplicate_groups = None

    if args.duplicates:
        duplicate_groups = find_exact_duplicates(metadata_items)
        print("")
        print("Exact duplicate groups")
        if not duplicate_groups:
            print("No exact duplicate groups found.")
        else:
            for index, group in enumerate(duplicate_groups, start=1):
                print(
                    f"Group {index}: sha256={group.sha256} "
                    f"size={group.size_bytes} bytes files={len(group.files)}"
                )
                for metadata in group.files:
                    print(f"  - {metadata.relative_path.as_posix()}")

    if args.plan_duplicates or args.apply_duplicate_plan:
        if duplicate_groups is None:
            duplicate_groups = find_exact_duplicates(metadata_items)
        plan_items = build_duplicate_review_plan(duplicate_groups, args.folder)
        _print_duplicate_review_plan(plan_items)
        if not plan_items:
            return

        if args.apply_duplicate_plan:
            print("")
            if args.confirm != CONFIRM_APPLY_DUPLICATE_PLAN:
                print(
                    "Apply refused: pass "
                    "--confirm APPLY_DUPLICATE_PLAN to apply this plan."
                )
                return

            operation_log = apply_move_plan(plan_items, args.folder)
            if any(not result.success for result in operation_log.operations):
                print("Apply completed with failures.")
            else:
                print("Apply completed.")
            _print_operation_log(operation_log)

    review_candidates = None

    if args.review_candidates:
        review_candidates = detect_review_candidates(metadata_items)
        _print_review_candidates(review_candidates)

    if args.plan_review_candidates:
        if review_candidates is None:
            review_candidates = detect_review_candidates(metadata_items)
        review_plan_items = build_review_candidate_plan(
            review_candidates,
            args.folder,
        )
        _print_review_candidate_plan(review_plan_items)


def _print_duplicate_review_plan(plan_items: list[MovePlanItem]) -> None:
    print("")
    print("Dry-run duplicate review plan")
    print("Dry-run only: no files will be moved by this command.")
    if not plan_items:
        print("No duplicate review plan items found.")
        return

    for index, item in enumerate(plan_items, start=1):
        print(f"Planned action {index}: {item.operation}")
        print(f"  source: {item.source}")
        print(f"  destination: {item.destination}")
        print(f"  reason: {item.reason}")
        print(f"  confidence: {item.confidence}")
        print(f"  overwrite_risk: {item.overwrite_risk}")


def _print_review_candidates(candidates) -> None:
    print("")
    print("Review candidates")
    if not candidates:
        print("No candidates for review found.")
        return

    for index, candidate in enumerate(candidates, start=1):
        print(f"Candidate for review {index}: {candidate.file.relative_path.as_posix()}")
        print(f"  category: {candidate.category}")
        print(f"  reason: {candidate.reason}")
        print(f"  confidence: {candidate.confidence}")


def _print_review_candidate_plan(plan_items: list[MovePlanItem]) -> None:
    print("")
    print("Dry-run review candidate plan")
    print("Dry-run only: no files will be moved by this command.")
    if not plan_items:
        print("No review candidate plan items found.")
        return

    for index, item in enumerate(plan_items, start=1):
        print(f"Planned action {index}: {item.operation}")
        print(f"  source: {item.source}")
        print(f"  destination: {item.destination}")
        print(f"  reason: {item.reason}")
        print(f"  confidence: {item.confidence}")
        print(f"  overwrite_risk: {item.overwrite_risk}")


def _print_operation_log(operation_log: OperationLog) -> None:
    print(f"Operation log: {operation_log.log_path}")
    for index, result in enumerate(operation_log.operations, start=1):
        status = "success" if result.success else "failure"
        print(f"Result {index}: {status}")
        print(f"  source: {result.source}")
        print(f"  destination: {result.destination}")
        print(f"  message: {result.message}")


if __name__ == "__main__":
    main()
