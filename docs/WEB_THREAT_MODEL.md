# Local Web Threat Model

Status: mandatory Stage 11 security contract, accepted in Stage 11.0.

This threat model applies to bootAI's single-user local web application. It is concrete to bootAI's root-bound scan, review, apply, verification, history, and restore workflows. It is not a claim that localhost is inherently trusted.

See [WEB_ARCHITECTURE.md](WEB_ARCHITECTURE.md) for layer ownership and [ADR 0002](adr/0002-web-security-boundary.md) for the boundary decision.

## Scope and Assumptions

The initial web application:

- runs on the user's computer;
- binds only to loopback;
- serves one validated immutable root per process;
- uses one worker and in-process state;
- is single-user and not a LAN, remote, cloud, or multi-user service;
- does not permanently delete files or integrate with Trash;
- treats browser values and loaded JSON artifacts as untrusted.

Malware already executing with the user's full filesystem permissions is outside the protection offered by an HTTP boundary. The application must still resist malicious websites, malformed or tampered artifacts, stale browser state, accidental replay, and path-boundary attacks.

## Protected Assets

- User files under the selected root.
- Reviewed decisions and approved plans.
- Organization rules and review state.
- Scan reports, apply results, verification reports, operation logs, and undo-result logs.
- The immutable validated root configuration.
- Launch, session, and CSRF secrets.
- Application code and bundled frontend assets.
- The integrity and ordering of scan, review, apply, verification, and restore workflows.

## Trust Boundaries

```text
external website
    ↕ untrusted browser/network requests
browser
    ↕ authenticated localhost HTTP session
localhost web server
    ↕ typed application-service calls
application services
    ↕ validated domain inputs and artifacts
deterministic bootAI modules
    ↕ executor-owned movement boundary
filesystem
```

The browser is untrusted even after session establishment. HTML forms, HTMX requests, URLs, headers, cookies, row IDs, revision values, and hidden fields can all be forged. Existing JSON artifacts are untrusted when loaded because users or other programs can edit them.

## Security Invariants

- Bind only to `127.0.0.1`; never use `0.0.0.0` by default.
- Accept only expected loopback Host values.
- Lock one resolved and validated root for the process lifetime.
- Never accept browser-provided source or destination paths.
- Use stable, session-scoped IDs to recover server-held paths and revalidate them.
- GET and HEAD are read-only. State changes require POST.
- Every state-changing request requires a valid signed session, session-bound CSRF token, same-origin validation, and current revision.
- Route modules never import or call `executor.py`.
- Apply and restore require fresh preflight, exact confirmation, an operation lock, and existing executor functions.
- Existing destinations are never overwritten.
- All frontend runtime assets are local and governed by a restrictive CSP.
- One process permits at most one active scan job and one active execution or restore operation.

## Threats and Required Mitigations

| Threat | Impact | Mandatory controls | First enforcing stage |
| --- | --- | --- | --- |
| Malicious external website sends requests to localhost | Unauthorized decision, apply, restore, or configuration action | one-time launch token, signed session, `SameSite=Strict`, CSRF, Origin validation, no CORS, POST-only mutations | 11.2 foundation; each later mutation stage |
| Forged state-changing request | Review or filesystem state changes without user intent | session-bound CSRF token, same-origin check, allowed action validation, POST-only mutation | 11.2 and every mutation stage |
| Host-header or DNS-rebinding-style request | External origin reaches localhost service under attacker-controlled host | bind to loopback IP, Trusted Host allowlist for expected loopback hosts, reject unknown Host, no LAN binding | 11.2 |
| Browser submits an arbitrary source or destination | Read, move, or expose a file chosen by an attacker | stable session IDs only; server-held path mapping; root, type, symlink, and artifact revalidation | 11.2 onward |
| `..`, absolute path, or symlink escapes the root | Access or movement outside the selected root | immutable resolved root; reject absolute/traversal values in artifacts; existing safety validation; executor preflight for movement | 11.1 onward |
| Stale tab overwrites newer decisions | Lost review work or incorrect approval | per-session revision; compare-and-reject; conflict response and reload guidance; never silent merge | 11.6 |
| Duplicate form submission or double-click | Repeated decision, save, apply, or restore | operation nonce or equivalent idempotency key, revision check, server-side lock, Post/Redirect/Get; disabled buttons are feedback only | 11.5 for review; 11.8/11.9 for movement |
| Refresh repeats an operation | Second apply or restore attempt | no mutations on GET; redirect to a read-only result; consume one-time confirmation/operation token | 11.5 onward |
| Two tabs edit one review session | Conflicting decisions and stale saves | revision comparison, stale rejection, session-scoped state, explicit conflict display | 11.6 |
| Tampered reviewed-plan file | Forged paths, decisions, or conflicting moves | treat as untrusted; validate schema, relative paths, stable identities, conflicts, root containment, current filesystem state | existing validation and 11.6–11.8 |
| Tampered operation log | Unsafe or misleading restore | strict log validation, root containment, source/destination state checks, restore preflight, exact confirmation, executor undo only | existing validation and 11.9 |
| Source disappears or changes after review | Apply affects stale or unexpected state | fresh metadata/source check immediately before apply; revision invalidation; fail closed | 11.6–11.8 |
| Destination appears after review | Overwrite or collision | fresh preflight immediately before executor delegation; executor's existing no-overwrite check | 11.7–11.8 |
| Server interruption during an operation | Partial batch and uncertain state | executor operation log remains authoritative; surface partial results; verify current filesystem; never infer success from browser state | 11.8–11.9 |
| Unsafe file-preview endpoint | Arbitrary local file disclosure, active content, or resource exhaustion | no arbitrary path endpoint; session-scoped IDs; allowlisted types; size limits; safe disposition; do not render active HTML/SVG content inline without a separate design | any preview stage |
| LAN-visible binding | Other devices can reach a filesystem-capable service | loopback-only default and validation; no `0.0.0.0`; remote/LAN mode outside Stage 11 | 11.2 |
| Compromised CDN or remote script | Attacker executes code in the trusted origin | bundle HTMX, Bootstrap, icons, scripts, styles, and fonts locally; no analytics or external runtime assets; restrictive CSP | 11.2 |
| Move described as storage recovery | User acts on a false safety or capacity claim | distinguish potential duplicate bytes from actual recovered storage; no removal or Trash action in Stage 11 | every UI stage |

## Mandatory Security Controls

### Loopback binding and trusted hosts

The server binds to `127.0.0.1`. User-facing URLs may use `127.0.0.1` or `localhost`, and the Trusted Host allowlist accepts only the concrete loopback host forms the launcher emits. An unknown Host is rejected before route processing. The application does not enable LAN or remote access in Stage 11.

### Immutable root

The launcher resolves and validates one root before the web workflow starts. That root is immutable process configuration. A request cannot replace it. Changing roots requires stopping the process and launching a new validated root-bound process.

### One-time launch token

The launcher must:

```text
generate a cryptographically random token
open a tokenized loopback URL
validate the token once
create a signed browser session
invalidate the launch token
redirect to a clean URL
```

The token must not remain in navigation URLs, bookmarks, referrers, logs, or page markup after bootstrap. Reuse fails closed.

### Signed browser session

Generate a random per-launch signing secret. The session cookie is:

```text
HttpOnly
SameSite=Strict
host-only
browser-session lifetime
signed with the per-launch secret
```

`Secure` is appropriate when a later deployment actually uses HTTPS; Stage 11 does not invent remote or TLS hosting. The session stores or references only the minimum root-bound state required by the UI.

### CSRF and origin enforcement

Every state-changing request requires a CSRF token bound to the signed session. Validate `Origin` against the exact launcher origin for mutations and reject missing or mismatched origins unless a documented same-origin browser case is handled safely. Do not enable CORS.

State-changing actions include decisions, current-page bulk decisions, reviewed-plan saves, apply, restore, and configuration changes.

### Request methods and replay control

GET and HEAD are read-only. POST performs mutations. Apply, save, decision change, configuration change, and restore must never be triggered by GET.

After a successful POST, redirect or render a read-only result URL so refresh cannot repeat the mutation. Revision checks, single-use operation tokens where required, and server-side locks enforce idempotency; client-side button disabling is not a security control.

### Stable IDs and untrusted artifacts

The browser supplies stable IDs and allowed actions, never filesystem paths. The server looks up each ID in the current root-bound session and revalidates the resolved path before use.

Loaded JSON artifacts must pass their existing schema, path, conflict, and root checks. Apply and restore also require fresh filesystem preflight. A valid signature is not assumed for legacy JSON; correctness comes from strict validation and current-state checks.

### Revision and multi-tab protection

Every state-changing review request carries the revision it read. A successful mutation advances the revision. A request with an older revision receives a conflict response with understandable reload/review guidance. The backend never silently applies a stale decision over a newer one.

### Single-process jobs and operation locks

Use one process and one worker. Permit one active scan job and one active execution-or-restore operation per root-bound process. The backend rejects or queues a duplicate request explicitly; it must not start concurrent executor calls.

### Apply and restore gates

Apply is unavailable before Stage 11.8 and restore before Stage 11.9. Each requires:

1. an authenticated current session;
2. CSRF, Origin, and revision validation;
3. a fresh read-only preflight;
4. an exact typed confirmation tied to the current operation;
5. the server-side operation lock;
6. delegation through `execution_service.py` to existing executor functions;
7. authoritative operation or undo-result logging;
8. a read-only result and verification path.

If the server stops during execution, browser state is not proof of success. Operation logs and filesystem verification determine the result.

### File preview restrictions

Do not implement an endpoint such as:

```text
/files?path=<arbitrary path>
```

Any later preview design must use a current session-scoped ID, revalidate the mapped file under the locked root, permit only explicitly supported types and sizes, prevent browser execution of active content, and set safe content headers. Preview is not implied by Stage 11.0.

### Security headers and local assets

The web app must send, at minimum:

```text
Content-Security-Policy:
  default-src 'self';
  script-src 'self';
  style-src 'self';
  img-src 'self' data:;
  connect-src 'self';
  object-src 'none';
  base-uri 'none';
  frame-ancestors 'none';
  form-action 'self'
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
```

The exact CSP may become stricter as templates are implemented, but it may not add remote sources to support a CDN or analytics. All runtime frontend assets and notices are local.

## Failure Behavior

- Invalid session, CSRF, Origin, Host, ID, path, artifact, revision, or confirmation fails closed.
- User-facing errors state what changed, what did not change, and whether any files moved.
- A stale request preserves newer state and offers a safe reload path.
- A preflight failure performs no movement.
- Partial executor results are displayed as partial, retained in authoritative logs, and eligible for read-only verification.
- The UI never converts a failed or unknown operation into a success based on optimistic client state.

## Residual Risks and Deferred Work

- A process with the user's filesystem permissions can access what the user can access; root locking constrains bootAI requests but is not an OS sandbox.
- Local malware or a compromised Python environment is outside the browser threat boundary.
- HTTPS is not required for loopback Stage 11, so host, session, CSRF, Origin, and CSP controls remain essential.
- Multi-process, multi-user, LAN, remote, and cloud deployment require a new threat model and are not enabled by this contract.
- Native desktop packaging does not weaken the localhost controls when it launches the web UI.
- Permanent removal and Trash integration require separate product and threat-model decisions and are not part of Stage 11.

## Verification Expectations

Each implementation stage must add tests for the controls it introduces. At minimum, later security tests must cover unknown Host, non-loopback configuration, launch-token replay, unsigned or altered sessions, missing/wrong CSRF, wrong Origin, mutation by GET, arbitrary and traversal paths, symlink escape, stale revision, repeated POST, concurrent execution, tampered artifacts, changed sources, new destinations, and blocked arbitrary preview access.
