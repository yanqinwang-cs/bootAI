import argparse
from pathlib import Path

from organizer.duplicates import find_exact_duplicates
from organizer.executor import apply_move_plan, undo_operation_log
from organizer.grouping import build_organization_suggestions, find_project_groups
from organizer.llm_refinement import (
    build_refined_organization_suggestion,
    refine_project_groups_with_ollama,
)
from organizer.models import (
    LLMRefinement,
    MovePlanItem,
    OperationLog,
    OrganizationSuggestion,
    ProjectGroup,
    ReviewCandidate,
)
from organizer.ollama_client import OllamaClient
from organizer.planner import build_duplicate_review_plan
from organizer.review import build_review_candidate_plan, detect_review_candidates
from organizer.scanner import scan_directory

CONFIRM_APPLY_DUPLICATE_PLAN = "APPLY_DUPLICATE_PLAN"
CONFIRM_APPLY_ORGANIZATION_PLAN = "APPLY_ORGANIZATION_PLAN"
CONFIRM_APPLY_REFINED_ORGANIZATION_PLAN = "APPLY_REFINED_ORGANIZATION_PLAN"


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a read-only file metadata report.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--duplicates", action="store_true")
    parser.add_argument("--plan-duplicates", action="store_true")
    parser.add_argument("--apply-duplicate-plan", action="store_true")
    parser.add_argument("--apply-organization-plan", action="store_true")
    parser.add_argument("--apply-refined-organization-plan", action="store_true")
    parser.add_argument("--confirm", default=None)
    parser.add_argument("--undo-log", type=Path, default=None)
    parser.add_argument("--review-candidates", action="store_true")
    parser.add_argument("--plan-review-candidates", action="store_true")
    parser.add_argument("--project-groups", action="store_true")
    parser.add_argument("--plan-organization", action="store_true")
    parser.add_argument("--refine-groups", action="store_true")
    parser.add_argument("--plan-refined-organization", action="store_true")
    parser.add_argument("--llm-provider", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--ollama-host", default="http://localhost:11434")
    args = parser.parse_args()

    if args.undo_log is not None:
        if (
            args.duplicates
            or args.plan_duplicates
            or args.apply_duplicate_plan
            or args.apply_organization_plan
            or args.apply_refined_organization_plan
            or args.confirm is not None
            or args.review_candidates
            or args.plan_review_candidates
            or args.project_groups
            or args.plan_organization
            or args.refine_groups
            or args.plan_refined_organization
            or args.llm_provider is not None
            or args.llm_model is not None
        ):
            parser.error("--undo-log cannot be combined with planning or review flags")
        operation_log = undo_operation_log(args.undo_log, args.folder)
        print("Undo operation results")
        _print_operation_log(operation_log)
        return 0

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
            return 0

        if args.apply_duplicate_plan:
            print("")
            if args.confirm != CONFIRM_APPLY_DUPLICATE_PLAN:
                print(
                    "Apply refused: pass "
                    "--confirm APPLY_DUPLICATE_PLAN to apply this plan."
                )
                return 0

            return _apply_plan_items(plan_items, args.folder)

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

    project_groups = None

    if args.project_groups:
        project_groups = find_project_groups(metadata_items)
        _print_project_groups(project_groups)

    if args.plan_organization or args.apply_organization_plan:
        if project_groups is None:
            project_groups = find_project_groups(metadata_items)
        suggestions = build_organization_suggestions(project_groups, args.folder)
        _print_organization_suggestions(suggestions)
        plan_items = _flatten_plan_items(suggestions)
        if not plan_items:
            return 0

        if args.apply_organization_plan:
            print("")
            if args.confirm != CONFIRM_APPLY_ORGANIZATION_PLAN:
                print(
                    "Apply refused: pass "
                    "--confirm APPLY_ORGANIZATION_PLAN to apply this plan."
                )
                return 0

            print("Approved organization move")
            return _apply_plan_items(plan_items, args.folder)

    refinements = None

    if (
        args.refine_groups
        or args.plan_refined_organization
        or args.apply_refined_organization_plan
    ):
        _validate_llm_args(parser, args.llm_provider, args.llm_model)
        if project_groups is None:
            project_groups = find_project_groups(metadata_items)
        client = OllamaClient(
            model=args.llm_model,
            host=args.ollama_host,
        )
        try:
            refinements = refine_project_groups_with_ollama(project_groups, client)
        except (RuntimeError, ValueError) as error:
            parser.error(str(error))

    if args.refine_groups:
        _print_llm_refinements(refinements or [])

    if args.plan_refined_organization or args.apply_refined_organization_plan:
        refined_suggestions = [
            build_refined_organization_suggestion(group, refinement, args.folder)
            for group, refinement in zip(project_groups or [], refinements or [])
        ]
        _print_refined_organization_suggestions(refined_suggestions)
        plan_items = _flatten_plan_items(refined_suggestions)
        if not plan_items:
            return 0

        if args.apply_refined_organization_plan:
            print("")
            if args.confirm != CONFIRM_APPLY_REFINED_ORGANIZATION_PLAN:
                print(
                    "Apply refused: pass "
                    "--confirm APPLY_REFINED_ORGANIZATION_PLAN to apply this plan."
                )
                return 0

            print("Approved refined organization move")
            return _apply_plan_items(plan_items, args.folder)

    return 0


def _validate_llm_args(
    parser: argparse.ArgumentParser,
    llm_provider: str | None,
    llm_model: str | None,
) -> None:
    if llm_provider != "ollama":
        parser.error("--llm-provider ollama is required for LLM refinement")
    if not llm_model:
        parser.error("--llm-model is required for LLM refinement")


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


def _print_review_candidates(candidates: list[ReviewCandidate]) -> None:
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


def _print_project_groups(groups: list[ProjectGroup]) -> None:
    print("")
    print("Project group suggestions")
    if not groups:
        print("No suggested groups found.")
        return

    for index, group in enumerate(groups, start=1):
        print(f"Suggested group {index}: {group.group_name}")
        print(f"  confidence: {group.confidence}")
        print(f"  reason: {group.reason}")
        print("  files:")
        for file in group.files:
            print(f"    - {file.relative_path.as_posix()}")


def _print_organization_suggestions(
    suggestions: list[OrganizationSuggestion],
) -> None:
    print("")
    print("Dry-run organization plan")
    print("Dry-run only: no files will be moved by this command.")
    if not suggestions:
        print("No candidate organization plan items found.")
        return

    for suggestion in suggestions:
        print(f"Candidate organization: {suggestion.group.group_name}")
        print(f"  suggested_root: {suggestion.suggested_root}")
        for index, item in enumerate(suggestion.plan_items, start=1):
            print(f"  Planned action {index}: {item.operation}")
            print(f"    source: {item.source}")
            print(f"    destination: {item.destination}")
            print(f"    reason: {item.reason}")
            print(f"    confidence: {item.confidence}")
            print(f"    overwrite_risk: {item.overwrite_risk}")


def _print_llm_refinements(refinements: list[LLMRefinement]) -> None:
    print("")
    print("LLM group refinements")
    if not refinements:
        print("No LLM refinements found.")
        return

    for index, refinement in enumerate(refinements, start=1):
        print(f"LLM refinement {index}: {refinement.original_group_name}")
        print(f"  refined_folder: {refinement.folder_name}")
        print(f"  confidence: {refinement.confidence}")
        print(f"  reason: {refinement.reason}")
        print("  warnings:")
        if refinement.warnings:
            for warning in refinement.warnings:
                print(f"    - {warning}")
        else:
            print("    - none")
        print("  subfolders:")
        for relative_path, subfolder in sorted(refinement.subfolders.items()):
            print(f"    - {relative_path}: {subfolder}")


def _print_refined_organization_suggestions(
    suggestions: list[OrganizationSuggestion],
) -> None:
    print("")
    print("Dry-run refined organization plan")
    print("Dry-run only: no files will be moved by this command.")
    if not suggestions:
        print("No refined organization plan items found.")
        return

    for suggestion in suggestions:
        print(f"Candidate organization: {suggestion.group.group_name}")
        print(f"  suggested_root: {suggestion.suggested_root}")
        for index, item in enumerate(suggestion.plan_items, start=1):
            print(f"  Planned action {index}: {item.operation}")
            print(f"    source: {item.source}")
            print(f"    destination: {item.destination}")
            print(f"    reason: {item.reason}")
            print(f"    confidence: {item.confidence}")
            print(f"    overwrite_risk: {item.overwrite_risk}")


def _flatten_plan_items(
    suggestions: list[OrganizationSuggestion],
) -> list[MovePlanItem]:
    return [
        item
        for suggestion in suggestions
        for item in suggestion.plan_items
    ]


def _apply_plan_items(plan_items: list[MovePlanItem], root: Path) -> int:
    operation_log = apply_move_plan(plan_items, root)
    if any(not result.success for result in operation_log.operations):
        print("Apply completed with failures.")
        _print_operation_log(operation_log)
        return 1

    print("Apply completed.")
    _print_operation_log(operation_log)
    return 0


def _print_operation_log(operation_log: OperationLog) -> None:
    print(f"Operation log: {operation_log.log_path}")
    for index, result in enumerate(operation_log.operations, start=1):
        status = "success" if result.success else "failure"
        print(f"Result {index}: {status}")
        print(f"  source: {result.source}")
        print(f"  destination: {result.destination}")
        print(f"  message: {result.message}")


if __name__ == "__main__":
    raise SystemExit(main())
