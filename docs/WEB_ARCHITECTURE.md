# Local Web Architecture Contract

Status: accepted in Stage 11.0; implemented through the Stage 11.1 service boundary.

This document freezes the architecture that all Stage 11 web work must follow. Stage 11.0 was documentation only. Stage 11.1 now provides shared application services and dependency hygiene, but still adds no server, routes, web dependencies, templates, static assets, CLI flags, or packaging behavior.

The companion [web threat model](WEB_THREAT_MODEL.md) defines the mandatory security controls. The architecture decisions are also recorded in [ADR 0001](adr/0001-local-web-stack.md), [ADR 0002](adr/0002-web-security-boundary.md), and [ADR 0003](adr/0003-application-service-layer.md).

## Product Direction

The local web application is bootAI's intended primary interface for ordinary users. It is for nontechnical users who need help finding files, understanding duplicate groups, remembering where files belong, reviewing organization suggestions, recovering from mistaken moves, and identifying potential storage-recovery candidates.

The interfaces have distinct roles:

- The local web application is the primary consumer interface.
- The CLI remains supported for development, scripting, diagnostics, manual fallback, and safety-critical testing.
- Static HTML remains a permanent, read-only report and audit-snapshot format. It does not become an interactive web application.
- A native desktop application is optional, demand-driven, and deferred until after core Stage 11 work.

## Stage 11.0 Record and Stage 11.1 Boundary

Stage 11.0 did not add or modify:

- `src/organizer/web/` or `src/organizer/application/`;
- FastAPI, Uvicorn, Jinja2, HTMX, or Bootstrap dependencies or files;
- routes, forms, sessions, cookies, CSRF code, jobs, templates, or static assets;
- scanner, grouping, review, executor, undo, verification, or report behavior;
- JSON schemas, reviewed-plan formats, report formats, or CLI flags;
- databases, native UI code, launchers, browser-opening code, or packaging;
- cloud APIs, telemetry, permanent removal, or Trash integration.

Stage 11.1 adds `application/scan_service.py`, `review_service.py`, `artifact_service.py`, and `view_models.py`. It does not add `application/preflight_service.py`, `application/execution_service.py`, `src/organizer/web/`, or web dependencies. Artifact loading is deliberately limited to scan reports and reviewed plans; later execution and history artifacts remain deferred.

## Current Ownership That Must Be Preserved

The current implementation already separates facts, review decisions, movement, verification, and audit artifacts. Later web work must reuse these owners:

| Current module | Preserved ownership |
| --- | --- |
| `safety.py` | shared root-containment validation |
| `review_session.py` | review rows, stable IDs, decisions, filtering, sorting, pagination, saving, saved-plan validation, and conflict detection |
| `executor.py` | movement-specific source/destination/symlink preflight, all real movement, operation logs, and undo |
| `organization_verify.py` | read-only post-apply verification |
| `reports.py` | report assembly and JSON report writing |
| `html_report.py` | static, read-only HTML rendering |
| `cli.py` | substantial current user-flow orchestration that will be extracted incrementally |

The shared validator in `safety.py` is the root-containment authority. Movement-specific validation remains executor-owned because it is part of the movement boundary. `executor.py` is the only module that may implement moves or undo.

Existing JSON artifacts remain the authoritative persistence formats:

- scan reports;
- reviewed plans and review state;
- organization rules;
- operation and undo logs;
- apply results;
- verification reports.

## Required Dependency Direction

```text
Local browser
    ↓
Web interface layer
    ↓
Application-service layer
    ↓
Existing deterministic bootAI modules
    ↓
executor.py for explicitly approved movement and undo only
```

The browser is a display and interaction surface. It is not a source of trusted filesystem instructions. The web layer translates validated HTTP requests into application-service calls. Application services coordinate existing domain modules. They do not replace those modules.

### Forbidden dependency directions

```text
web route → executor.py
web route → raw filesystem movement
web route → duplicated scanner, duplicate, grouping, or review logic
template → filesystem operation
browser form → arbitrary absolute path
browser form → arbitrary destination path
web layer → CLI handler simulation
web layer → terminal input()
```

Web routes must never import `executor.py`. Only the future `execution_service.py` may delegate already validated and explicitly approved plans to existing executor functions.

## Application-Service Layer

Stage 11.1 introduces this package:

```text
src/organizer/application/
    __init__.py
    scan_service.py
    review_service.py
    artifact_service.py
    view_models.py
```

`preflight_service.py` and `execution_service.py` remain future ownership slots for Stages 11.7 and 11.8 or later. They do not exist in Stage 11.1.

### `scan_service.py`

- Coordinate scan workflows through the scanner, duplicate, review, grouping, and reporting modules.
- Return typed UI-independent results.
- Never perform terminal input, printing, HTML rendering, movement, or undo.

### `review_service.py`

- Create and resume sessions through `review_session.py`.
- Expose existing filters, sorting, pagination, stable-ID decisions, conflict checks, and saving.
- Never create a second review engine or silently merge stale decisions.

### `artifact_service.py`

- List and load only existing scan reports and reviewed plans for the first web MVP.
- Treat every loaded artifact as untrusted input.
- Resolve and validate artifact paths under the immutable process root.
- Delegate format validation to `reports.py` and `review_session.py`; defer all later artifact formats to their roadmap stages.

### Future `preflight_service.py`

- Perform read-only final-plan and restore checks.
- Detect missing or changed sources, existing destinations, conflicts, root escapes, symlink hazards, tampered artifacts, and stale revisions.
- Never move or restore files.

### Future `execution_service.py`

- Be the only application-service gateway to existing executor functions.
- Accept only a validated, current, explicitly approved plan.
- Enforce fresh preflight and exact confirmation before delegation.
- Return operation, apply, verification, and undo results without implementing movement.

### `view_models.py`

- Define typed presentation data shared by CLI and web presenters where appropriate.
- Contain no request objects, HTML, terminal I/O, or filesystem side effects.

## Future Web Interface Layer

The intended package is:

```text
src/organizer/web/
    __init__.py
    app.py
    server.py
    config.py
    security.py
    jobs.py
    presenters.py

    routes/
        home.py
        scan.py
        review.py
        plan.py
        execution.py
        history.py

    templates/
        base.html
        home.html
        scan.html
        review.html
        plan.html
        result.html
        history.html
        partials/

    static/
        css/
            bootai.css
        js/
            bootai.js
        vendor/
            htmx.min.js
            bootstrap.min.css
            bootstrap.bundle.min.js
        icons/
        THIRD_PARTY_NOTICES.txt
```

This layout is guidance for later stages. Stage 11.0 must not create it.

The web layer may own routes, forms, HTTP request validation, signed sessions, CSRF enforcement, templates, HTML fragments, presenters, security headers, and user-facing error rendering. It must not own scanning algorithms, duplicate detection, grouping logic, review validation, conflict detection, root safety, movement, undo, or operation-log construction.

## Browser Request Contract

The browser submits stable, session-scoped identifiers and allowed actions. The backend maps those identifiers to server-held state and revalidates the corresponding paths.

Conceptually accepted:

```text
row_id=O17
decision=approved
revision=12
csrf_token=<session-bound token>
```

Forbidden:

```text
source=/Users/name/Downloads/file.pdf
destination=/Users/name/Documents/file.pdf
```

State-changing requests must carry a current revision or equivalent version marker. A stale request is rejected and shown as a conflict; it is never silently merged over newer decisions.

## Root-Selection Contract

Each server process operates on exactly one root:

1. Select the root before or during launch.
2. Validate it with existing safety logic.
3. Store its resolved identity as immutable process configuration.
4. Map all session IDs and artifact access back to that root.

The browser cannot change the root by submitting path text. Changing roots requires ending the current root-bound server, validating another root, and starting a new process.

Development mode may eventually support:

```bash
bootai web
bootai web --root /path/to/folder
```

The default may be the current user's Downloads directory only when that behavior is explicitly documented and the directory passes validation. A packaged launcher may use a small native folder chooser before opening the browser; that does not make bootAI a native desktop application.

## Accepted Web Stack and Asset Policy

The accepted stack is:

```text
FastAPI
Jinja2
HTMX
Bootstrap
minimal vanilla JavaScript
Uvicorn
```

All assets must be bundled locally, including HTMX, Bootstrap CSS and JavaScript, icons, custom CSS and JavaScript, and any fonts. CDNs, remote fonts, analytics, telemetry, external scripts, and runtime cloud dependencies are forbidden. The application must remain usable without internet access.

Static HTML audit reports remain self-contained read-only documents. They do not gain routes, sessions, approval controls, or apply behavior.

## Server and Concurrency Policy

The eventual server configuration is:

```text
host: 127.0.0.1
port: dynamically selected when practical
workers: 1
root: one validated and immutable root per launch
```

It must never bind to `0.0.0.0` by default. LAN access, remote access, multi-user hosting, and cloud deployment are outside Stage 11.

Use a single process and one worker initially. Permit at most one active scan job and one active execution or restore operation in a root-bound process. UI button disabling is only feedback; server-side locks, revisions, idempotency controls, and fresh preflight provide the actual protection.

## Persistence Policy

Do not introduce a database initially. Existing JSON artifacts remain authoritative. Temporary interface state may remain in memory:

- filters, sort, page, and page size;
- dirty-state and current revision;
- scan-job status;
- launch and session tokens;
- CSRF token;
- one-operation locks and replay-prevention state.

A database may be considered only after measured evidence shows a need. It must not become a prerequisite merely to host a single-user localhost UI.

## Security Contract

Localhost is a network security boundary, not a reason to omit security. Later implementation must include loopback-only binding, a one-time launch token, a signed browser-session cookie, session-bound CSRF, same-origin enforcement, Trusted Host validation, read-only GET requests, mutation-only POST requests, restrictive response headers, revision checks, and no CORS. Details and threat-to-control mappings are mandatory in [WEB_THREAT_MODEL.md](WEB_THREAT_MODEL.md).

## Accessibility Contract

Target WCAG 2.2 AA from the first web screen. Every Stage 11 interface must provide:

- complete keyboard access and logical focus order;
- clearly visible focus indicators;
- semantic HTML and labelled controls;
- accessible tables, dialogs, errors, and validation guidance;
- status and progress announcements where appropriate;
- sufficient contrast and no information conveyed by color alone;
- no drag-only interaction;
- usable browser zoom and reflow.

Accessibility is an implementation requirement, not a final packaging pass. Stage 11.10 performs the formal audit and hardening.

## Storage-Recovery Language

Moving a file to another folder on the same filesystem does not save storage space. The interface may report:

- `Potential duplicate bytes`;
- `Potential recoverable storage`;
- `Duplicate candidates for review`.

It must not report `Space saved` or `Storage recovered` unless an operation actually removes data from that filesystem or transfers it elsewhere. Stage 11 adds no permanent removal, Trash integration, automatic disposal, or disposal-safety claims.

## CLI Migration Policy

Do not rewrite `cli.py` in one large refactor. Extract one use case at a time in Stage 11.1 and later:

```text
CLI → application service
Web UI → same application service
```

Preserve existing CLI behavior and tests during each extraction. CLI and web flows must not develop separate scan, review, preflight, execution, or restore implementations.

Stage 11.1 removes the former mandatory `openai` and `python-dotenv` dependencies and their transitive lockfile packages. Core dependencies are empty and package discovery is restricted to `src/`. The historical OpenRouter assistant is preserved only under `legacy/openrouter_code_assistant/`, outside bootAI packaging and runtime. Optional FastAPI/Jinja2/Uvicorn dependencies remain deferred until Stage 11.2.

## Packaging Goal

The later development workflow may become:

```bash
python -m pip install -e ".[web]"
bootai web
```

The end-user target is:

```text
download
double-click
choose or accept Downloads
browser opens automatically
```

Packaging belongs to Stage 11.10. A packaged application should hide terminal setup from ordinary users. macOS is the first packaging target and Windows follows later.

## Stage 11 Sequence

### Stage 11.0 — Architecture Contract and Threat Model

Documentation only: stack, ownership, threat model, security controls, accessibility, and complete roadmap.

### Stage 11.1 — Application Services and Dependency Hygiene

Completed: UI-independent scan, immutable review-session, and scan-report/reviewed-plan artifact services; narrow CLI entry migration; mandatory cloud dependency removal; and historical OpenRouter archival. Optional web dependencies remain deferred. No server and no movement changes.

### Stage 11.2 — Secure Local Web Shell and Launcher

Add the FastAPI app factory, loopback-only launcher, dynamic port, automatic browser opening, one-time launch token, signed session, CSRF foundation, Trusted Host validation, CSP, base template, and local assets. No scan yet.

### Stage 11.3 — Read-Only Scan Dashboard

Add an explicit user-triggered scan, one in-process scan job, progress polling, failure handling, report generation, and summary cards. No decisions or movement.

### Stage 11.4 — Read-Only Review Explorer

Browse review rows, filter, sort, paginate, inspect details, and inspect conflicts. No decision mutation.

### Stage 11.5 — Review Decisions and Reviewed-Plan Saving

Add Organize, Keep here, and Review later decisions; current-page confirmed bulk decisions; dirty state; explicit save; and collision-safe reviewed-plan artifacts. No movement.

### Stage 11.6 — Resume, Stale-State, and Multi-Tab Protection

Resume reviewed plans; add revision protection, stale-form rejection, multi-tab conflict handling, and source/destination change detection. No movement.

### Stage 11.7 — Final Plan Preview and Execution Preflight

Show exact source/destination plans and check missing sources, destination collisions, root and symlink safety, and stale metadata. No movement.

### Stage 11.8 — Confirmed Web Apply and Verification

Require fresh preflight, exact typed confirmation, CSRF and revision checks, and one execution at a time. Reuse reviewed-plan validation and `executor.py`, write operation/apply artifacts, and run post-apply verification.

### Stage 11.9 — History, Verification, and Confirmed Restore

Show operation history and verification, then require restore preflight and exact confirmation before delegating to existing executor undo and writing undo-result logs.

### Stage 11.10 — Packaging, Onboarding, Accessibility, and Release Hardening

Add low-setup packaging, macOS-first and Windows-later launchers, no visible terminal for ordinary users, native folder selection, clean shutdown, an accessibility audit, large-folder performance testing, and nontechnical-user testing.

Native desktop development remains an optional final extension after Stage 11.

## Stage 11.5 MVP Checkpoint

Stage 11.5 is the first product-evaluation checkpoint. A user should be able to launch the development web interface, scan a folder, understand findings, inspect suggestions, make review decisions, and save a valid reviewed plan.

Apply and undo may still be CLI-only at this checkpoint. Evaluate the product workflow with target users before automatically continuing to web execution stages. Core Stage 11 does not have to be complete before usability is tested.
