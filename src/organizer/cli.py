import argparse
from pathlib import Path

from organizer.duplicates import find_exact_duplicates
from organizer.scanner import scan_directory


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a read-only file metadata report.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--duplicates", action="store_true")
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

    if args.duplicates:
        duplicate_groups = find_exact_duplicates(metadata_items)
        print("")
        print("Exact duplicate groups")
        if not duplicate_groups:
            print("No exact duplicate groups found.")
            return

        for index, group in enumerate(duplicate_groups, start=1):
            print(
                f"Group {index}: sha256={group.sha256} "
                f"size={group.size_bytes} bytes files={len(group.files)}"
            )
            for metadata in group.files:
                print(f"  - {metadata.relative_path.as_posix()}")


if __name__ == "__main__":
    main()
