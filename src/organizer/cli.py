import argparse
from pathlib import Path

from organizer.duplicates import find_exact_duplicates
from organizer.executor import apply_move_plan, undo_operation_log
from organizer.grouping import build_organization_suggestions, find_project_groups
from organizer.html_report import html_report_output_path, write_html_report
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
    ReviewedPlanItem,
)
from organizer.ollama_client import OllamaClient
from organizer.organization_apply_review import (
    CONFIRM_APPLY_ORGANIZATION_REVIEW,
    apply_approved_organization_review,
)
from organizer.organization_rules import load_organization_rules
from organizer.organization_review import export_organization_review
from organizer.planner import build_duplicate_review_plan
from organizer.reports import build_scan_report, default_report_path, write_report
from organizer.review import build_review_candidate_plan, detect_review_candidates
from organizer.rule_review import (
    apply_rule_decisions,
    export_rule_candidates,
    rule_candidates_from_report,
)
from organizer.review_session import (
    approve_items,
    approved_plan_items,
    build_review_session_items,
    find_approved_move_conflicts,
    get_item,
    load_reviewed_plan_move_items,
    reject_items,
    save_reviewed_plan,
    summarize_review_items,
)
from organizer.review_state import (
    ReviewState,
    apply_review_state_to_items,
    load_review_state,
    save_review_state,
    update_review_state_from_items,
)
from organizer.scanner import scan_directory

CONFIRM_APPLY_DUPLICATE_PLAN = "APPLY_DUPLICATE_PLAN"
CONFIRM_APPLY_ORGANIZATION_PLAN = "APPLY_ORGANIZATION_PLAN"
CONFIRM_APPLY_REFINED_ORGANIZATION_PLAN = "APPLY_REFINED_ORGANIZATION_PLAN"
CONFIRM_APPLY_REVIEWED_PLAN = "APPLY_REVIEWED_PLAN"
CONFIRM_APPLY_ORGANIZATION_RULES = "APPLY ORGANIZATION RULES"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a read-only file metadata report.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--duplicates", action="store_true")
    parser.add_argument("--plan-duplicates", action="store_true")
    parser.add_argument("--apply-duplicate-plan", action="store_true")
    parser.add_argument("--apply-organization-plan", action="store_true")
    parser.add_argument("--apply-refined-organization-plan", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--html-report", action="store_true")
    parser.add_argument("--html-report-output", type=Path, default=None)
    parser.add_argument("--export-rule-candidates", action="store_true")
    parser.add_argument("--rule-candidates-output", type=Path, default=None)
    parser.add_argument("--apply-rule-decisions", type=Path, default=None)
    parser.add_argument("--export-organization-review", action="store_true")
    parser.add_argument("--organization-review-output", type=Path, default=None)
    parser.add_argument("--apply-organization-review", type=Path, default=None)
    parser.add_argument("--review-plans", action="store_true")
    parser.add_argument("--ignore-review-state", action="store_true")
    parser.add_argument("--apply-reviewed-plan", type=Path, default=None)
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
    parser.add_argument("--ollama-host", default=None)
    args = parser.parse_args()

    if args.report_output is not None and not args.report:
        parser.error("--report-output requires --report")
    if args.html_report_output is not None and not args.html_report:
        parser.error("--html-report-output requires --html-report")
    if args.rule_candidates_output is not None and not args.export_rule_candidates:
        parser.error("--rule-candidates-output requires --export-rule-candidates")
    if (
        args.organization_review_output is not None
        and not args.export_organization_review
    ):
        parser.error(
            "--organization-review-output requires --export-organization-review"
        )
    if args.ignore_review_state and not args.review_plans:
        parser.error("--ignore-review-state requires --review-plans")

    if args.apply_organization_review is not None:
        return _handle_apply_organization_review(parser, args)

    if args.export_organization_review:
        return _handle_export_organization_review(parser, args)

    if args.export_rule_candidates:
        return _handle_export_rule_candidates(parser, args)

    if args.apply_rule_decisions is not None:
        return _handle_apply_rule_decisions(parser, args)

    if args.html_report:
        return _handle_html_report(parser, args)

    if args.apply_reviewed_plan is not None:
        return _handle_apply_reviewed_plan(parser, args)

    if args.report:
        return _handle_report(parser, args)

    if args.review_plans:
        return _handle_review_plans(parser, args)

    if args.undo_log is not None:
        if (
            args.duplicates
            or args.plan_duplicates
            or args.apply_duplicate_plan
            or args.apply_organization_plan
            or args.apply_refined_organization_plan
            or args.html_report
            or args.html_report_output is not None
            or args.apply_reviewed_plan is not None
            or args.export_rule_candidates
            or args.rule_candidates_output is not None
            or args.apply_rule_decisions is not None
            or args.confirm is not None
            or args.review_candidates
            or args.plan_review_candidates
            or args.project_groups
            or args.plan_organization
            or args.review_plans
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
    organization_rules = load_organization_rules(args.folder).rules
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
        plan_items = build_duplicate_review_plan(
            duplicate_groups,
            args.folder,
            all_metadata=metadata_items,
        )
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
        project_groups = find_project_groups(metadata_items, rules=organization_rules)
        _print_project_groups(project_groups)

    if args.plan_organization or args.apply_organization_plan:
        if project_groups is None:
            project_groups = find_project_groups(metadata_items, rules=organization_rules)
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
            project_groups = find_project_groups(metadata_items, rules=organization_rules)
        client = OllamaClient(
            model=args.llm_model,
            host=args.ollama_host or DEFAULT_OLLAMA_HOST,
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


def _handle_review_plans(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> int:
    if (
        args.duplicates
        or args.plan_duplicates
        or args.apply_duplicate_plan
        or args.apply_organization_plan
        or args.apply_refined_organization_plan
        or args.apply_reviewed_plan is not None
        or args.export_rule_candidates
        or args.rule_candidates_output is not None
        or args.apply_rule_decisions is not None
        or args.report
        or args.report_output is not None
        or args.confirm is not None
        or args.undo_log is not None
        or args.review_candidates
        or args.plan_review_candidates
        or args.project_groups
        or args.plan_organization
        or args.refine_groups
        or args.plan_refined_organization
        or args.llm_provider is not None
        or args.llm_model is not None
        or args.ollama_host is not None
    ):
        parser.error(
            "--review-plans cannot be combined with display, planning, apply, "
            "undo, report, LLM, or confirmation flags"
        )

    metadata_items = scan_directory(args.folder, max_depth=args.max_depth)
    items = build_review_session_items(metadata_items, args.folder)
    state: ReviewState | None = None
    if args.ignore_review_state:
        print("Review state ignored for this session.")
    else:
        try:
            state = load_review_state(args.folder)
        except ValueError as error:
            parser.error(str(error))
        if state.decisions:
            items = apply_review_state_to_items(items, state, args.folder)
            print(f"Review state loaded: {len(state.decisions)} remembered decision(s).")
        else:
            print("No review state found; starting with new suggestions.")

    if not items:
        print("No duplicate, organization, or review-candidate move candidates found for review.")
        return 0

    print("Batch review session")
    print("Approve/reject commands update review decisions only; they do not move files.")
    _print_review_session_help()
    _print_review_session_summary(items, args.folder)
    saved_current_plan_path: Path | None = None

    while True:
        try:
            command_line = input("review> ").strip()
        except EOFError:
            print("")
            print("Exiting review session without applying.")
            return 0

        if not command_line:
            continue

        command = command_line.split()
        action = command[0].lower()

        try:
            if action == "help" and len(command) == 1:
                _print_review_session_help()
            elif action == "show" and len(command) == 2 and command[1].lower() == "duplicates":
                _print_review_session_rows(items, "duplicate", args.folder)
            elif action == "show" and len(command) == 2 and command[1].lower() == "organization":
                _print_review_session_rows(items, "organization", args.folder)
            elif action == "show" and len(command) == 2 and command[1].lower() == "review-candidates":
                _print_review_session_rows(items, "review_candidate", args.folder)
            elif action == "summary" and len(command) == 1:
                _print_review_session_summary(items, args.folder)
            elif action == "conflicts" and len(command) == 1:
                _print_review_session_conflicts(items, args.folder)
            elif action == "reject" and len(command) > 1:
                items = reject_items(items, command[1:])
                saved_current_plan_path = None
                print(f"Rejected {len(command) - 1} reviewed plan item(s).")
            elif action == "approve" and len(command) > 1:
                items = approve_items(items, command[1:])
                saved_current_plan_path = None
                print(f"Approved {len(command) - 1} reviewed plan item(s).")
            elif action == "details" and len(command) == 2:
                _print_review_session_item(get_item(items, command[1]), args.folder)
            elif action == "save" and len(command) == 1:
                saved_current_plan_path = save_reviewed_plan(items, args.folder)
                print(f"Reviewed plan saved: {saved_current_plan_path}")
                state = _save_review_state_for_items(items, args.folder, state)
            elif action == "apply" and len(command) == 1:
                _print_review_session_summary(items, args.folder)
                plan_items = approved_plan_items(items)
                if not plan_items:
                    print("No approved moves to apply.")
                    continue
                conflicts = find_approved_move_conflicts(items, args.folder)
                if conflicts:
                    print(
                        "Apply blocked: one or more source or destination paths "
                        "have multiple approved moves."
                    )
                    _print_review_session_conflicts(items, args.folder)
                    continue
                if saved_current_plan_path is None:
                    saved_current_plan_path = save_reviewed_plan(items, args.folder)
                    print(f"Reviewed plan saved: {saved_current_plan_path}")
                confirmation = input("Type APPLY_REVIEWED_PLAN to continue: ")
                if confirmation != CONFIRM_APPLY_REVIEWED_PLAN:
                    print("Apply refused: exact confirmation was not provided.")
                    continue
                state = _save_review_state_for_items(items, args.folder, state)
                print("Applying approved moves from reviewed plan.")
                return _apply_plan_items(plan_items, args.folder)
            elif action == "quit" and len(command) == 1:
                print("Exiting review session without applying.")
                return 0
            else:
                print("Unknown command. Type help for available commands.")
        except ValueError as error:
            print(f"Error: {error}")


def _handle_apply_reviewed_plan(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> int:
    if (
        args.duplicates
        or args.plan_duplicates
        or args.apply_duplicate_plan
        or args.apply_organization_plan
        or args.apply_refined_organization_plan
        or args.export_rule_candidates
        or args.rule_candidates_output is not None
        or args.apply_rule_decisions is not None
        or args.report
        or args.report_output is not None
        or args.undo_log is not None
        or args.review_plans
        or args.review_candidates
        or args.plan_review_candidates
        or args.project_groups
        or args.plan_organization
        or args.refine_groups
        or args.plan_refined_organization
        or args.llm_provider is not None
        or args.llm_model is not None
    ):
        parser.error(
            "--apply-reviewed-plan cannot be combined with display, planning, "
            "apply, undo, report, review, or LLM flags"
        )

    if args.confirm != CONFIRM_APPLY_REVIEWED_PLAN:
        print(
            "Apply refused: pass --confirm APPLY_REVIEWED_PLAN "
            "to apply this reviewed plan."
        )
        return 0

    try:
        plan_items = load_reviewed_plan_move_items(args.apply_reviewed_plan, args.folder)
        print(f"Reviewed plan approved moves: {len(plan_items)}")
        if not plan_items:
            print("No approved moves to apply.")
            return 0
        print("Applying approved moves from saved reviewed plan.")
        return _apply_plan_items(plan_items, args.folder)
    except ValueError as error:
        parser.error(str(error))


def _handle_export_rule_candidates(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> int:
    if (
        args.duplicates
        or args.plan_duplicates
        or args.apply_duplicate_plan
        or args.apply_organization_plan
        or args.apply_refined_organization_plan
        or args.apply_reviewed_plan is not None
        or args.apply_rule_decisions is not None
        or args.report
        or args.report_output is not None
        or args.html_report
        or args.html_report_output is not None
        or args.confirm is not None
        or args.undo_log is not None
        or args.review_plans
        or args.ignore_review_state
        or args.review_candidates
        or args.plan_review_candidates
        or args.project_groups
        or args.plan_organization
        or args.refine_groups
        or args.plan_refined_organization
        or args.llm_provider is not None
        or args.llm_model is not None
    ):
        parser.error("--export-rule-candidates cannot be combined with other report, planning, apply, review, undo, LLM, or confirmation flags")

    try:
        report = build_scan_report(args.folder, max_depth=args.max_depth)
        candidates = rule_candidates_from_report(report)
        output_path = export_rule_candidates(
            candidates,
            args.folder,
            args.rule_candidates_output,
        )
    except ValueError as error:
        parser.error(str(error))

    print(f"Rule candidates exported: {output_path}")
    print(f"Candidates: {len(candidates)}")
    print("Review the file manually, then apply accepted decisions with exact confirmation.")
    return 0


def _handle_export_organization_review(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> int:
    if (
        args.duplicates
        or args.plan_duplicates
        or args.apply_duplicate_plan
        or args.apply_organization_plan
        or args.apply_refined_organization_plan
        or args.apply_reviewed_plan is not None
        or args.export_rule_candidates
        or args.rule_candidates_output is not None
        or args.apply_rule_decisions is not None
        or args.report
        or args.report_output is not None
        or args.html_report
        or args.html_report_output is not None
        or args.confirm is not None
        or args.undo_log is not None
        or args.review_plans
        or args.ignore_review_state
        or args.review_candidates
        or args.plan_review_candidates
        or args.project_groups
        or args.plan_organization
        or args.refine_groups
        or args.plan_refined_organization
        or args.llm_provider is not None
        or args.llm_model is not None
        or args.ollama_host is not None
    ):
        parser.error(
            "--export-organization-review may be combined only with --max-depth"
        )

    try:
        report = build_scan_report(args.folder, max_depth=args.max_depth)
        output_path = export_organization_review(
            report,
            args.folder,
            args.organization_review_output,
        )
    except ValueError as error:
        parser.error(str(error))

    item_count = report["summary"]["organization_suggestion_count"]
    print(f"Organization review exported: {output_path}")
    print(f"Suggestions: {item_count}")
    print("Decisions default to undecided. This command does not move files.")
    return 0


def _handle_apply_organization_review(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> int:
    if (
        args.max_depth is not None
        or args.duplicates
        or args.plan_duplicates
        or args.apply_duplicate_plan
        or args.apply_organization_plan
        or args.apply_refined_organization_plan
        or args.apply_reviewed_plan is not None
        or args.export_organization_review
        or args.organization_review_output is not None
        or args.export_rule_candidates
        or args.rule_candidates_output is not None
        or args.apply_rule_decisions is not None
        or args.report
        or args.report_output is not None
        or args.html_report
        or args.html_report_output is not None
        or args.undo_log is not None
        or args.review_plans
        or args.ignore_review_state
        or args.review_candidates
        or args.plan_review_candidates
        or args.project_groups
        or args.plan_organization
        or args.refine_groups
        or args.plan_refined_organization
        or args.llm_provider is not None
        or args.llm_model is not None
        or args.ollama_host is not None
    ):
        parser.error(
            "--apply-organization-review cannot be combined with other modes or --max-depth"
        )

    if args.confirm != CONFIRM_APPLY_ORGANIZATION_REVIEW:
        print(
            'Apply refused: pass --confirm "APPLY ORGANIZATION REVIEW" '
            "to apply approved organization review rows."
        )
        return 0

    try:
        outcome = apply_approved_organization_review(
            args.apply_organization_review,
            args.folder,
            args.confirm,
        )
    except ValueError as error:
        parser.error(str(error))

    print(f"Approved rows: {outcome.approved_count}")
    print(f"Applied rows: {outcome.applied_count}")
    print(f"Skipped rows: {outcome.skipped_count}")
    print(f"Failed rows: {outcome.failed_count}")
    print(f"Apply result: {outcome.result_path}")

    if outcome.operation_log is None:
        print("No approved organization review rows to apply.")
        return 0

    if outcome.failed_count:
        print("Apply completed with failures.")
        _print_operation_log(outcome.operation_log)
        return 1

    print("Apply completed.")
    _print_operation_log(outcome.operation_log)
    return 0


def _handle_apply_rule_decisions(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> int:
    if (
        args.max_depth is not None
        or args.duplicates
        or args.plan_duplicates
        or args.apply_duplicate_plan
        or args.apply_organization_plan
        or args.apply_refined_organization_plan
        or args.apply_reviewed_plan is not None
        or args.export_rule_candidates
        or args.rule_candidates_output is not None
        or args.report
        or args.report_output is not None
        or args.html_report
        or args.html_report_output is not None
        or args.undo_log is not None
        or args.review_plans
        or args.ignore_review_state
        or args.review_candidates
        or args.plan_review_candidates
        or args.project_groups
        or args.plan_organization
        or args.refine_groups
        or args.plan_refined_organization
        or args.llm_provider is not None
        or args.llm_model is not None
    ):
        parser.error("--apply-rule-decisions cannot be combined with scan, display, planning, apply, review, undo, report, or LLM flags")

    if args.confirm != CONFIRM_APPLY_ORGANIZATION_RULES:
        print(
            'Rule decision apply refused: pass --confirm "APPLY ORGANIZATION RULES" '
            "to update organization_rules.json."
        )
        return 0

    try:
        result_path = apply_rule_decisions(args.apply_rule_decisions, args.folder)
    except ValueError as error:
        parser.error(str(error))

    print("Organization rule decisions applied.")
    print(f"Apply result log: {result_path}")
    print("No files were moved by this command.")
    return 0


def _save_review_state_for_items(
    items: list[ReviewedPlanItem],
    root: Path,
    current_state: ReviewState | None,
) -> ReviewState:
    if current_state is None:
        current_state = load_review_state(root)
    updated_state = update_review_state_from_items(current_state, items, root)
    path = save_review_state(updated_state, root)
    print(f"Review state saved: {path}")
    return updated_state


def _print_review_session_help() -> None:
    print(
        "Commands: help, show duplicates, show organization, show review-candidates, "
        "summary, conflicts, reject <IDs...>, approve <IDs...>, details <ID>, "
        "save, apply, quit"
    )


def _print_review_session_rows(
    items: list[ReviewedPlanItem],
    category: str,
    root: Path,
) -> None:
    matching_items = [item for item in items if item.category == category]
    title = (
        "Duplicate move candidates"
        if category == "duplicate"
        else "Organization move candidates"
        if category == "organization"
        else "Review-candidate suggested moves"
    )
    print("")
    print(title)
    if not matching_items:
        print("No candidates for this category.")
        return
    for item in matching_items:
        _print_review_session_item_summary(item, root)


def _print_review_session_item_summary(
    item: ReviewedPlanItem,
    root: Path,
) -> None:
    plan_item = item.plan_item
    print(
        f"{item.id} [{_review_session_decision_label(item)}] "
        f"{_relative_to_root(plan_item.source, root)} -> "
        f"{_relative_to_root(plan_item.destination, root)}"
    )


def _print_review_session_item(
    item: ReviewedPlanItem,
    root: Path,
) -> None:
    plan_item = item.plan_item
    print(f"{item.id}")
    print(f"  category: {item.category}")
    if item.review_category is not None:
        print(f"  review_category: {item.review_category}")
    print(f"  decision: {item.decision}")
    print(f"  memory_status: {item.memory_status}")
    if item.remembered_decision is not None:
        print(f"  remembered_decision: {item.remembered_decision}")
    print(f"  source: {_relative_to_root(plan_item.source, root)}")
    print(f"  destination: {_relative_to_root(plan_item.destination, root)}")
    print(f"  reason: {plan_item.reason}")
    print(f"  confidence: {plan_item.confidence}")
    print(f"  operation: {plan_item.operation}")
    print(f"  overwrite_risk: {plan_item.overwrite_risk}")


def _print_review_session_summary(
    items: list[ReviewedPlanItem],
    root: Path,
) -> None:
    summary = summarize_review_items(items, root)
    print("")
    print("Review summary")
    print(f"  duplicate approved moves: {summary['duplicate_approved_move_count']}")
    print(f"  duplicate rejected moves: {summary['duplicate_rejected_move_count']}")
    print(f"  organization approved moves: {summary['organization_approved_move_count']}")
    print(f"  organization rejected moves: {summary['organization_rejected_move_count']}")
    print(
        "  review candidate approved moves: "
        f"{summary['review_candidate_approved_move_count']}"
    )
    print(
        "  review candidate rejected moves: "
        f"{summary['review_candidate_rejected_move_count']}"
    )
    print(f"  total approved moves: {summary['approved_move_count']}")
    print(f"  total rejected moves: {summary['rejected_move_count']}")
    print(f"  approved source conflicts: {summary['approved_source_conflict_count']}")
    print(f"  approved destination conflicts: {summary['approved_destination_conflict_count']}")
    print(f"  approved move conflicts: {summary['approved_move_conflict_count']}")
    print(f"  new suggestions: {summary['memory_new_suggestion_count']}")
    print(f"  remembered rejected decisions: {summary['memory_rejected_remembered_count']}")
    print(f"  remembered approved decisions: {summary['memory_approved_remembered_count']}")
    print(f"  stale prior decisions: {summary['memory_stale_prior_decision_count']}")
    if summary["approved_move_conflict_count"]:
        print("  final apply is blocked until conflicts are resolved")


def _review_session_decision_label(item: ReviewedPlanItem) -> str:
    if item.memory_status == "rejected_remembered":
        return "rejected remembered"
    if item.memory_status == "approved_remembered":
        return "approved remembered"
    if item.memory_status == "stale_prior_decision":
        return "stale prior decision"
    return item.decision


def _print_review_session_conflicts(
    items: list[ReviewedPlanItem],
    root: Path,
) -> None:
    conflicts = find_approved_move_conflicts(items, root)
    print("")
    print("Approved move conflicts")
    if not conflicts:
        print("No approved move conflicts found.")
        return

    for conflict in conflicts:
        if conflict.conflict_type == "source":
            print(f"Source conflict: {conflict.relative_path}")
            guidance = "Reject all but one approved move for the same source."
        else:
            print(f"Destination conflict: {conflict.relative_path}")
            guidance = "Reject all but one approved move targeting the same destination."
        for item in conflict.items:
            plan_item = item.plan_item
            print(
                f"  {item.id} "
                f"{_relative_to_root(plan_item.source, root)} -> "
                f"{_relative_to_root(plan_item.destination, root)}"
            )
        print(guidance)


def _relative_to_root(path: Path, root: Path) -> str:
    resolved_root = root.resolve()
    try:
        return path.relative_to(resolved_root).as_posix()
    except ValueError:
        return path.as_posix()


def _handle_report(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> int:
    if (
        args.duplicates
        or args.plan_duplicates
        or args.apply_duplicate_plan
        or args.apply_organization_plan
        or args.apply_refined_organization_plan
        or args.confirm is not None
        or args.undo_log is not None
        or args.html_report
        or args.html_report_output is not None
        or args.review_plans
        or args.review_candidates
        or args.plan_review_candidates
        or args.project_groups
        or args.plan_organization
        or args.plan_refined_organization
    ):
        parser.error("--report cannot be combined with display, planning, apply, undo, or confirmation flags")

    if args.refine_groups:
        _validate_llm_args(parser, args.llm_provider, args.llm_model)
        client = OllamaClient(
            model=args.llm_model,
            host=args.ollama_host or DEFAULT_OLLAMA_HOST,
        )
    else:
        if args.llm_provider is not None or args.llm_model is not None:
            parser.error("--llm-provider and --llm-model require --refine-groups in report mode")
        client = None

    try:
        report = build_scan_report(
            args.folder,
            max_depth=args.max_depth,
            refine_groups=args.refine_groups,
            llm_client=client,
        )
        report_path = write_report(report, args.folder, args.report_output)
    except ValueError as error:
        parser.error(str(error))

    if report["warnings"]:
        print(f"Report written with warnings: {report_path}")
    else:
        print(f"Report written: {report_path}")
    return 0


def _handle_html_report(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> int:
    if (
        args.report
        or args.report_output is not None
        or args.duplicates
        or args.plan_duplicates
        or args.apply_duplicate_plan
        or args.apply_organization_plan
        or args.apply_refined_organization_plan
        or args.apply_reviewed_plan is not None
        or args.confirm is not None
        or args.undo_log is not None
        or args.review_plans
        or args.ignore_review_state
        or args.review_candidates
        or args.plan_review_candidates
        or args.project_groups
        or args.plan_organization
        or args.plan_refined_organization
    ):
        parser.error(
            "--html-report cannot be combined with display, planning, apply, "
            "review, undo, report, or confirmation flags"
        )

    if args.refine_groups:
        _validate_llm_args(parser, args.llm_provider, args.llm_model)
        client = OllamaClient(
            model=args.llm_model,
            host=args.ollama_host or DEFAULT_OLLAMA_HOST,
        )
    else:
        if args.llm_provider is not None or args.llm_model is not None:
            parser.error("--llm-provider and --llm-model require --refine-groups in HTML report mode")
        client = None

    try:
        resolved_root = args.folder.resolve()
        json_report_path = default_report_path(resolved_root)
        html_report_path = html_report_output_path(
            resolved_root,
            json_report_path=json_report_path,
            output_path=args.html_report_output,
        )
        if html_report_path == json_report_path:
            raise ValueError("HTML report output must be different from JSON report output")
        report = build_scan_report(
            args.folder,
            max_depth=args.max_depth,
            refine_groups=args.refine_groups,
            llm_client=client,
        )
        written_json_path = write_report(report, args.folder, json_report_path)
        written_html_path = write_html_report(
            report,
            args.folder,
            json_report_path=written_json_path,
            output_path=html_report_path,
        )
    except ValueError as error:
        parser.error(str(error))

    if report["warnings"]:
        print(f"HTML report written with warnings: {written_html_path}")
    else:
        print(f"HTML report written: {written_html_path}")
    print(f"JSON report written: {written_json_path}")
    return 0


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
