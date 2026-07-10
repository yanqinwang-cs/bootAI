# ADR 0003: Application-Service Layer

Status: accepted in Stage 11.0.

## Context

`cli.py` currently performs substantial orchestration and directly calls existing executor functions. Adding routes that reproduce CLI handlers or call the executor would create parallel workflow implementations and blur the movement boundary.

## Decision

Introduce UI-independent application services incrementally in Stage 11.1 and later:

```text
CLI ─┐
     ├→ application services → deterministic modules → executor.py
Web ─┘                                      approved movement/undo only
```

The intended package contains `scan_service.py`, `review_service.py`, `artifact_service.py`, `preflight_service.py`, `execution_service.py`, and `view_models.py`.

- Scan service coordinates existing scan/report modules and returns typed results.
- Review service exposes `review_session.py` behavior without a second review engine.
- Artifact service loads existing JSON as untrusted root-bound input.
- Preflight service performs read-only current-state checks.
- Execution service is the only application-service gateway to existing executor functions.
- View models contain UI-independent presentation data.

Web routes may validate HTTP requests and render responses, but they never import `executor.py`, implement filesystem movement, reproduce deterministic algorithms, simulate CLI handlers, or invoke terminal input. Templates never perform filesystem operations.

Migrate one use case at a time. Preserve CLI behavior and tests, then have the CLI and web UI call the same service where practical. Do not rewrite the CLI in one large refactor.

## Consequences

- Stage 11.1 must establish dependency hygiene before adding the server.
- Services need typed results and explicit errors suitable for both CLI and web presenters.
- Existing deterministic module ownership, JSON formats, confirmations, executor behavior, and undo semantics remain authoritative.
- Temporary duplication may exist only during a bounded extraction; two lasting implementations of one workflow are prohibited.

## Rejected Alternatives

- **Routes call `executor.py` directly:** rejected because it bypasses the use-case, preflight, confirmation, and audit boundary.
- **Routes invoke or simulate CLI handlers:** rejected because terminal I/O and HTTP request lifecycles have different concerns.
- **A separate web review engine:** rejected because decisions, stable IDs, validation, conflicts, filtering, and pagination already belong to `review_session.py`.
- **A single large CLI rewrite:** rejected because it creates unnecessary regression risk and obscures stage-by-stage safety review.
