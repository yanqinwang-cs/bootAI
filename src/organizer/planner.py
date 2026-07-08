from pathlib import Path

from organizer.models import DuplicateGroup, FileMetadata, MovePlanItem


def choose_reference_file(group: DuplicateGroup) -> FileMetadata:
    if not group.files:
        raise ValueError("duplicate group must contain at least one file")

    return sorted(
        group.files,
        key=lambda metadata: (
            len(metadata.relative_path.as_posix()),
            metadata.relative_path.as_posix(),
        ),
    )[0]


def build_duplicate_review_plan(
    duplicate_groups: list[DuplicateGroup],
    root: Path,
    review_folder_name: str = "AI_Review",
) -> list[MovePlanItem]:
    plan_items: list[MovePlanItem] = []

    for group in duplicate_groups:
        reference = choose_reference_file(group)
        reference_relative_path = reference.relative_path.as_posix()

        for metadata in sorted(
            group.files,
            key=lambda item: item.relative_path.as_posix(),
        ):
            if metadata == reference:
                continue

            destination = (
                root
                / review_folder_name
                / "duplicates"
                / metadata.relative_path
            )
            plan_items.append(
                MovePlanItem(
                    source=metadata.path,
                    destination=destination,
                    reason=f"exact duplicate of {reference_relative_path}",
                    confidence=100,
                    operation="dry-run move",
                    overwrite_risk=destination.exists(),
                )
            )

    return plan_items
