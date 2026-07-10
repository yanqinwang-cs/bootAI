from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import socket
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch

from organizer.web.config import WebAppConfig
from organizer.web import server


class _HealthyResponse:
    status = 200

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeSocket:
    def __init__(self, port: int = 43210) -> None:
        self.port = port
        self.closed = False

    def getsockname(self) -> tuple[str, int]:
        return (server.LOOPBACK_HOST, self.port)

    def close(self) -> None:
        self.closed = True


class _FakeBindingSocket(_FakeSocket):
    def __init__(
        self,
        port: int = 43210,
        *,
        bind_error: OSError | None = None,
    ) -> None:
        super().__init__(port)
        self.bind_error = bind_error
        self.bound_address: tuple[str, int] | None = None
        self.backlog: int | None = None
        self.inheritable: bool | None = None

    def bind(self, address: tuple[str, int]) -> None:
        self.bound_address = address
        if self.bind_error is not None:
            raise self.bind_error

    def listen(self, backlog: int) -> None:
        self.backlog = backlog

    def set_inheritable(self, value: bool) -> None:
        self.inheritable = value


class WebServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.config = WebAppConfig(
            self.root,
            session_secret="s" * 32,
            launch_token="t" * 32,
            testing=True,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_parser_supports_only_root_no_browser_and_valid_fixed_port(self) -> None:
        parser = server.build_parser()
        args = parser.parse_args(
            ["--root", str(self.root), "--no-browser", "--port", "8123"]
        )

        self.assertEqual(args.root, self.root)
        self.assertTrue(args.no_browser)
        self.assertEqual(args.port, 8123)
        self.assertNotIn("--host", parser.format_help())

        for invalid in ("0", "65536", "not-a-port"):
            with self.subTest(port=invalid), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    parser.parse_args(["--port", invalid])

    def test_omitted_root_fails_clearly_when_downloads_is_unavailable(self) -> None:
        missing_home = self.root / "missing-home"
        stderr = StringIO()
        with patch.object(Path, "home", return_value=missing_home):
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                server.main(["--no-browser"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Downloads", stderr.getvalue())
        self.assertIn("does not exist", stderr.getvalue())

    def test_dynamic_and_fixed_sockets_bind_only_to_ipv4_loopback(self) -> None:
        dynamic = _FakeBindingSocket(port=41001)
        fixed = _FakeBindingSocket(port=8123)
        socket_constructor = Mock(side_effect=[dynamic, fixed])

        with patch.object(server.socket, "socket", socket_constructor):
            self.assertIs(server.bind_loopback_socket(), dynamic)
            self.assertIs(server.bind_loopback_socket(8123), fixed)

        self.assertEqual(dynamic.bound_address, (server.LOOPBACK_HOST, 0))
        self.assertEqual(fixed.bound_address, (server.LOOPBACK_HOST, 8123))
        self.assertEqual(dynamic.backlog, server._SOCKET_BACKLOG)
        self.assertTrue(dynamic.inheritable)
        self.assertEqual(
            socket_constructor.call_args_list[0].args,
            (socket.AF_INET, socket.SOCK_STREAM),
        )

    def test_occupied_fixed_port_has_a_clear_error(self) -> None:
        occupied = _FakeBindingSocket(bind_error=OSError("address in use"))
        with patch.object(server.socket, "socket", return_value=occupied):
            with self.assertRaisesRegex(server.WebServerError, "port 8123"):
                server.bind_loopback_socket(8123)

        self.assertTrue(occupied.closed)

    def test_browser_is_opened_only_after_health_succeeds(self) -> None:
        response = _HealthyResponse()
        health_opener = Mock(return_value=response)
        browser_opener = Mock(return_value=True)
        stdout = StringIO()

        with redirect_stdout(stdout):
            server._open_browser_when_ready(
                "http://127.0.0.1:4000/healthz",
                "http://127.0.0.1:4000/launch/private-token",
                Event(),
                health_opener=health_opener,
                browser_opener=browser_opener,
            )

        health_opener.assert_called_once_with(
            "http://127.0.0.1:4000/healthz",
            timeout=0.25,
        )
        browser_opener.assert_called_once_with(
            "http://127.0.0.1:4000/launch/private-token"
        )
        self.assertTrue(response.closed)
        self.assertEqual(stdout.getvalue(), "")

    def test_browser_failure_prints_the_single_use_url(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            server._open_browser_when_ready(
                "http://127.0.0.1:4000/healthz",
                "http://127.0.0.1:4000/launch/private-token",
                Event(),
                health_opener=Mock(return_value=_HealthyResponse()),
                browser_opener=Mock(return_value=False),
            )

        self.assertIn("temporary private URL", stdout.getvalue())
        self.assertIn("/launch/private-token", stdout.getvalue())

    def test_no_browser_uses_one_worker_and_always_closes_socket(self) -> None:
        fake_socket = _FakeSocket()
        fake_uvicorn_server = Mock()
        config_constructor = Mock(return_value="uvicorn-config")
        stdout = StringIO()

        with (
            patch.object(server, "bind_loopback_socket", return_value=fake_socket),
            patch.object(server.uvicorn, "Config", config_constructor),
            patch.object(server.uvicorn, "Server", return_value=fake_uvicorn_server),
            redirect_stdout(stdout),
        ):
            result = server.run_server(
                self.config,
                port=43210,
                open_browser=False,
            )

        self.assertEqual(result, 0)
        self.assertTrue(fake_socket.closed)
        fake_uvicorn_server.run.assert_called_once_with(sockets=[fake_socket])
        options = config_constructor.call_args.kwargs
        self.assertEqual(options["host"], "127.0.0.1")
        self.assertEqual(options["port"], 43210)
        self.assertEqual(options["workers"], 1)
        self.assertFalse(options["reload"])
        self.assertFalse(options["access_log"])
        self.assertFalse(options["proxy_headers"])
        self.assertIn("/launch/" + self.config.launch_token, stdout.getvalue())

    def test_socket_is_closed_when_uvicorn_exits_with_an_error(self) -> None:
        fake_socket = _FakeSocket()
        fake_uvicorn_server = Mock()
        fake_uvicorn_server.run.side_effect = RuntimeError("server failed")

        with (
            patch.object(server, "bind_loopback_socket", return_value=fake_socket),
            patch.object(server.uvicorn, "Config", return_value="config"),
            patch.object(server.uvicorn, "Server", return_value=fake_uvicorn_server),
            redirect_stdout(StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "server failed"):
                server.run_server(self.config, open_browser=False)

        self.assertTrue(fake_socket.closed)

    def test_keyboard_interrupt_is_a_clean_shutdown(self) -> None:
        fake_socket = _FakeSocket()
        fake_uvicorn_server = Mock()
        fake_uvicorn_server.run.side_effect = KeyboardInterrupt()

        with (
            patch.object(server, "bind_loopback_socket", return_value=fake_socket),
            patch.object(server.uvicorn, "Config", return_value="config"),
            patch.object(server.uvicorn, "Server", return_value=fake_uvicorn_server),
            redirect_stdout(StringIO()),
        ):
            result = server.run_server(self.config, open_browser=False)

        self.assertEqual(result, 0)
        self.assertTrue(fake_socket.closed)

    def test_browser_readiness_thread_is_started_joined_and_token_safe(self) -> None:
        fake_socket = _FakeSocket()
        fake_thread = Mock()
        fake_uvicorn_server = Mock()
        stdout = StringIO()

        with (
            patch.object(server, "bind_loopback_socket", return_value=fake_socket),
            patch.object(server.uvicorn, "Config", return_value="config"),
            patch.object(server.uvicorn, "Server", return_value=fake_uvicorn_server),
            patch.object(server, "Thread", return_value=fake_thread) as thread_type,
            redirect_stdout(stdout),
        ):
            self.assertEqual(server.run_server(self.config), 0)

        fake_thread.start.assert_called_once_with()
        fake_thread.join.assert_called_once_with()
        self.assertTrue(fake_socket.closed)
        self.assertNotIn(self.config.launch_token, stdout.getvalue())
        thread_args = thread_type.call_args.kwargs["args"]
        self.assertEqual(thread_args[0], "http://127.0.0.1:43210/healthz")
        self.assertEqual(
            thread_args[1],
            "http://127.0.0.1:43210/launch/" + self.config.launch_token,
        )
        self.assertTrue(thread_args[2].is_set())


if __name__ == "__main__":
    unittest.main()
