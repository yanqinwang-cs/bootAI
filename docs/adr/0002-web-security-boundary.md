# ADR 0002: Local Web Security Boundary

Status: accepted in Stage 11.0.

## Context

A localhost application can receive requests initiated by malicious external websites, stale tabs, forged forms, or modified browser state. It also loads user-editable JSON artifacts and can eventually trigger filesystem movement. Loopback binding alone is not sufficient protection.

## Decision

Treat the browser, every browser-provided value, and every loaded JSON artifact as untrusted.

Each process locks one validated root and binds only to `127.0.0.1`. The launch flow uses a one-time random token to establish a signed, host-only, browser-lifetime session cookie with `HttpOnly` and `SameSite=Strict`, then redirects to a clean URL.

Every mutation uses POST and requires a current signed session, session-bound CSRF token, same-origin validation, an allowed action, and a current revision. GET remains read-only. Trusted Host validation rejects unexpected hosts, CORS is disabled, and restrictive security headers are mandatory.

Browser requests use stable session-scoped IDs, never arbitrary source or destination paths. The server maps IDs to root-bound server state and revalidates paths and artifacts. There is no arbitrary file-serving endpoint.

Apply and restore add fresh preflight, exact typed confirmation, replay protection, a server-side operation lock, and delegation through the application-service boundary to existing executor functions.

## Consequences

- Local development and packaged launchers must bootstrap a browser session rather than expose an unauthenticated root page.
- State-changing route tests must cover session, CSRF, Origin, Host, method, revision, and replay failures.
- Multi-tab edits are rejected when stale instead of being silently merged.
- LAN, remote, multi-user, and cloud hosting are incompatible with this threat model and require a new decision.

## Rejected Alternatives

- **No security because the server is local:** rejected because external websites and forged browser requests can target localhost.
- **Launch token on every URL:** rejected because tokens can leak through history, logs, and copied URLs; it is single-use session bootstrap only.
- **Browser-provided filesystem paths:** rejected because hidden fields and requests are attacker-controlled.
- **Client-side disabled buttons as concurrency control:** rejected because requests can be replayed; locks and revisions are server-side.
- **Default LAN binding:** rejected because it exposes a filesystem-capable service outside the single-user boundary.
