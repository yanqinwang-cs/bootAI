import argparse
from pathlib import Path

from organizer.duplicates import find_exact_duplicates
from organizer.planner import build_duplicate_review_plan
from organizer.scanner import scan_directory


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a read-only file metadata report.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--duplicates", action="store_true")
    parser.add_argument("--plan-duplicates", action="store_true")
    args = parser.parse_args()

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

    if args.plan_duplicates:
        if duplicate_groups is None:
            duplicate_groups = find_exact_duplicates(metadata_items)
        plan_items = build_duplicate_review_plan(duplicate_groups, args.folder)
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


if __name__ == "__main__":
    main()
