import hmac
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest import mock

from starlette.requests import Request

from organizer.web.security import (
    CSRF_SESSION_KEY,
    LaunchTokenGate,
    WebSecurityError,
    csrf_token_for_session,
    initialize_authenticated_session,
    is_authenticated,
    validate_csrf_token,
    validate_same_origin,
)


class WebSecurityTests(unittest.TestCase):
    def test_launch_token_is_constant_time_and_single_use(self) -> None:
        token = "a" * 32
        gate = LaunchTokenGate(token)
        with mock.patch(
            "organizer.web.security.hmac.compare_digest",
            wraps=hmac.compare_digest,
        ) as compare:
            self.assertFalse(gate.consume("wrong"))
            self.assertFalse(gate.consume(""))
            self.assertTrue(gate.consume(token))
            self.assertFalse(gate.consume(token))

        self.assertTrue(gate.consumed)
        self.assertGreaterEqual(compare.call_count, 4)

    def test_launch_token_concurrent_use_has_one_winner(self) -> None:
        token = "b" * 32
        gate = LaunchTokenGate(token)
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(gate.consume, [token] * 16))

        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 15)

    def test_csrf_token_is_session_bound_and_constant_time(self) -> None:
        first: dict[str, object] = {}
        second: dict[str, object] = {}
        first_token = initialize_authenticated_session(first)
        second_token = initialize_authenticated_session(second)

        self.assertTrue(is_authenticated(first))
        self.assertEqual(csrf_token_for_session(first), first_token)
        self.assertNotEqual(first_token, second_token)
        with mock.patch(
            "organizer.web.security.hmac.compare_digest",
            wraps=hmac.compare_digest,
        ) as compare:
            validate_csrf_token(first, first_token)
            with self.assertRaises(WebSecurityError):
                validate_csrf_token(first, second_token)
        self.assertEqual(compare.call_count, 2)

    def test_csrf_rejects_missing_wrong_and_unauthenticated_tokens(self) -> None:
        session: dict[str, object] = {}
        token = initialize_authenticated_session(session)
        for submitted in (None, "", "wrong"):
            with self.subTest(submitted=submitted):
                with self.assertRaises(WebSecurityError):
                    validate_csrf_token(session, submitted)

        unauthenticated = {CSRF_SESSION_KEY: token}
        with self.assertRaises(WebSecurityError):
            csrf_token_for_session(unauthenticated)
        with self.assertRaises(WebSecurityError):
            validate_csrf_token(unauthenticated, token)

    def test_same_origin_accepts_exact_loopback_origins(self) -> None:
        validate_same_origin(
            _request("127.0.0.1:8123", ["http://127.0.0.1:8123"])
        )
        validate_same_origin(
            _request("localhost:8123", ["http://localhost:8123"])
        )
        validate_same_origin(
            _request(
                "localhost:443",
                ["https://localhost:443"],
                scheme="https",
            )
        )

    def test_same_origin_rejects_untrusted_or_malformed_origins(self) -> None:
        cases = (
            ("127.0.0.1:8123", []),
            ("127.0.0.1:8123", ["null"]),
            ("127.0.0.1:8123", ["http://127.0.0.1:9999"]),
            ("127.0.0.1:8123", ["https://127.0.0.1:8123"]),
            ("127.0.0.1:8123", ["http://localhost:8123"]),
            ("127.0.0.1:8123", ["http://192.168.1.4:8123"]),
            ("127.0.0.1:8123", ["http://example.com:8123"]),
            ("127.0.0.1:8123", ["http://user@127.0.0.1:8123"]),
            ("127.0.0.1:8123", ["http://127.0.0.1:8123/path"]),
            ("127.0.0.1:8123", ["http://127.0.0.1:8123?query"]),
            ("127.0.0.1:8123", ["http://127.0.0.1:8123#fragment"]),
            ("127.0.0.1:8123", ["://malformed"]),
            (
                "127.0.0.1:8123",
                ["http://127.0.0.1:8123", "http://127.0.0.1:8123"],
            ),
        )
        for host, origins in cases:
            with self.subTest(origins=origins):
                with self.assertRaises(WebSecurityError):
                    validate_same_origin(_request(host, list(origins)))


def _request(
    host: str,
    origins: list[str],
    *,
    scheme: str = "http",
) -> Request:
    headers = [(b"host", host.encode("ascii"))]
    headers.extend((b"origin", origin.encode("ascii")) for origin in origins)
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": scheme,
            "path": "/future-mutation",
            "raw_path": b"/future-mutation",
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8123),
        }
    )


if __name__ == "__main__":
    unittest.main()
