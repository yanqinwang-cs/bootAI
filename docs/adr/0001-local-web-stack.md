# ADR 0001: Local Web Stack

Status: accepted in Stage 11.0.

## Context

bootAI needs a primary interface suitable for nontechnical users while preserving explicit review, confirmation, apply, verification, and restore boundaries. It must run offline, package with low setup, and keep deterministic Python modules as the source of truth.

## Decision

Use a local web application with:

```text
FastAPI
Jinja2
HTMX
Bootstrap
minimal vanilla JavaScript
Uvicorn
```

Bundle all runtime frontend assets locally. Do not use CDNs, remote fonts, analytics, telemetry, external scripts, or runtime cloud dependencies. Bind to loopback only and use one worker initially.

The web application is the primary consumer interface. The CLI remains supported for development, scripting, diagnostics, fallback, and safety testing. Static HTML remains read-only. Native desktop work is optional and deferred until after Stage 11.

## Consequences

- Server-rendered HTML and explicit HTTP mutations keep transactional boundaries visible and auditable.
- HTMX supplies focused partial updates without a second full client-side state system.
- Python packaging remains the main application toolchain.
- Local asset ownership increases packaging responsibility but preserves offline use and supply-chain control.
- Accessibility and security must be implemented in templates and routes from the first screen.

## Rejected or Deferred Alternatives

### Streamlit

Rejected as the main architecture because interactions commonly rerun application scripts and transactional state is less explicit. bootAI needs controlled review, confirmation, apply, and undo workflows.

### NiceGUI

Rejected as the main architecture because framework-managed persistent WebSocket/UI state adds unnecessary complexity. Explicit request/response routes are easier to audit. NiceGUI remains acceptable for unrelated prototypes.

### React or Vue SPA

Rejected initially because it requires Node/npm and a frontend build system, adds a second major application-state layer, and increases setup and packaging complexity without an initial SPA-level requirement.

### Native desktop UI

Deferred because it has the highest cross-platform implementation and packaging cost and would distract from validating the product workflow. A small packaged folder chooser does not change this decision.

### Terminal-only UI

Rejected as the primary consumer interface because the target audience is not primarily developers and terminal workflows create avoidable setup and usability barriers. The CLI remains supported.
