from pathlib import Path

from organizer.models import DuplicateGroup, FileMetadata, MovePlanItem
from organizer.scope import is_actionable_plan_eligible


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
    all_metadata: list[FileMetadata] | None = None,
) -> list[MovePlanItem]:
    plan_items: list[MovePlanItem] = []
    metadata_context = (
        all_metadata
        if all_metadata is not None
        else [
            metadata
            for group in duplicate_groups
            for metadata in group.files
        ]
    )

    for group in duplicate_groups:
        eligible_files = [
            metadata
            for metadata in group.files
            if is_actionable_plan_eligible(metadata, metadata_context)
        ]
        if len(eligible_files) < 2:
            continue

        eligible_group = DuplicateGroup(
            sha256=group.sha256,
            size_bytes=group.size_bytes,
            files=eligible_files,
        )
        reference = choose_reference_file(eligible_group)
        reference_relative_path = reference.relative_path.as_posix()

        for metadata in sorted(
            eligible_files,
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
