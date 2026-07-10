from __future__ import annotations

from collections.abc import Mapping, MutableMapping
import hmac
import secrets
from threading import Lock
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

AUTHENTICATED_SESSION_KEY = "authenticated"
CSRF_SESSION_KEY = "csrf_token"
SESSION_ID_KEY = "session_id"

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    )
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}


class WebSecurityError(ValueError):
    pass


class LaunchTokenGate:
    def __init__(self, token: str) -> None:
        self._token = token
        self._consumed = False
        self._lock = Lock()

    def consume(self, candidate: str) -> bool:
        supplied = candidate if isinstance(candidate, str) else ""
        with self._lock:
            matches = hmac.compare_digest(supplied, self._token)
            if self._consumed or not supplied or not matches:
                return False
            self._consumed = True
            return True

    @property
    def consumed(self) -> bool:
        with self._lock:
            return self._consumed


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


def apply_security_headers(response: Response) -> Response:
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


def initialize_authenticated_session(
    session: MutableMapping[str, object],
) -> str:
    csrf_token = secrets.token_urlsafe(32)
    session.clear()
    session[AUTHENTICATED_SESSION_KEY] = True
    session[SESSION_ID_KEY] = secrets.token_urlsafe(24)
    session[CSRF_SESSION_KEY] = csrf_token
    return csrf_token


def is_authenticated(session: Mapping[str, object]) -> bool:
    return session.get(AUTHENTICATED_SESSION_KEY) is True


def csrf_token_for_session(session: Mapping[str, object]) -> str:
    if not is_authenticated(session):
        raise WebSecurityError("authenticated session required")
    token = session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        raise WebSecurityError("session CSRF token is unavailable")
    return token


def validate_csrf_token(
    session: Mapping[str, object],
    submitted_token: str | None,
) -> None:
    expected = csrf_token_for_session(session)
    candidate = submitted_token if isinstance(submitted_token, str) else ""
    if not candidate or not hmac.compare_digest(candidate, expected):
        raise WebSecurityError("invalid CSRF token")


def validate_same_origin(request: Request) -> None:
    origin_values = request.headers.getlist("origin")
    if len(origin_values) != 1:
        raise WebSecurityError("exactly one Origin header is required")

    origin_text = origin_values[0]
    if not origin_text or origin_text == "null":
        raise WebSecurityError("Origin header is invalid")
    try:
        origin = urlsplit(origin_text)
        request_port = _effective_port(request.url.scheme, request.url.port)
        origin_port = _effective_port(origin.scheme, origin.port)
    except ValueError as error:
        raise WebSecurityError("Origin header is malformed") from error

    request_host = (request.url.hostname or "").lower()
    origin_host = (origin.hostname or "").lower()
    if (
        origin.scheme not in {"http", "https"}
        or origin.scheme != request.url.scheme
        or request_host not in _LOOPBACK_HOSTS
        or origin_host != request_host
        or origin_host not in _LOOPBACK_HOSTS
        or origin_port != request_port
        or origin.username is not None
        or origin.password is not None
        or origin.path
        or origin.query
        or origin.fragment
    ):
        raise WebSecurityError("Origin does not match this bootAI session")


def _effective_port(scheme: str, port: int | None) -> int:
    if port is not None:
        return port
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    raise ValueError("unsupported URL scheme")
