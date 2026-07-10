from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from contextlib import closing
from pathlib import Path
import socket
import sys
from threading import Event, Thread
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

import uvicorn

from organizer.web.app import create_app
from organizer.web.config import WebAppConfig

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_READY_TIMEOUT_SECONDS = 5.0
_SOCKET_BACKLOG = 2048


class WebServerError(ValueError):
    pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.root if args.root is not None else Path.home() / "Downloads"
    try:
        config = WebAppConfig(root=root)
        return run_server(
            config,
            port=args.port,
            open_browser=not args.no_browser,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch bootAI's root-locked local web interface.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="folder locked to this web-server process (default: ~/Downloads)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="print a private launch URL instead of opening a browser",
    )
    parser.add_argument(
        "--port",
        type=_validated_port,
        default=None,
        help="fixed loopback port for development (default: dynamic)",
    )
    return parser


def run_server(
    config: WebAppConfig,
    *,
    port: int | None = None,
    open_browser: bool = True,
) -> int:
    bound_socket = bind_loopback_socket(port)
    stop_event = Event()
    readiness_thread: Thread | None = None
    actual_port = int(bound_socket.getsockname()[1])
    base_url = f"http://{LOOPBACK_HOST}:{actual_port}"
    health_url = f"{base_url}/healthz"
    launch_url = f"{base_url}/launch/{config.launch_token}"

    try:
        app = create_app(config)
        uvicorn_config = uvicorn.Config(
            app=app,
            host=LOOPBACK_HOST,
            port=actual_port,
            workers=1,
            reload=False,
            access_log=False,
            proxy_headers=False,
        )
        server = uvicorn.Server(uvicorn_config)

        if open_browser:
            readiness_thread = Thread(
                target=_open_browser_when_ready,
                args=(health_url, launch_url, stop_event),
                name="bootai-browser-launch",
            )
            readiness_thread.start()
        else:
            _print_manual_launch_url(launch_url)

        server.run(sockets=[bound_socket])
        return 0
    finally:
        stop_event.set()
        if readiness_thread is not None:
            readiness_thread.join()
        bound_socket.close()


def bind_loopback_socket(port: int | None = None) -> socket.socket:
    requested_port = 0 if port is None else _validated_port(str(port))
    bound_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        bound_socket.bind((LOOPBACK_HOST, requested_port))
        bound_socket.listen(_SOCKET_BACKLOG)
        bound_socket.set_inheritable(True)
    except OSError as error:
        bound_socket.close()
        label = "a dynamic port" if port is None else f"port {port}"
        raise WebServerError(
            f"could not bind {label} on {LOOPBACK_HOST}: {error}"
        ) from error
    return bound_socket


def _validated_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _open_browser_when_ready(
    health_url: str,
    launch_url: str,
    stop_event: Event,
    *,
    timeout_seconds: float = DEFAULT_READY_TIMEOUT_SECONDS,
    health_opener: Callable[..., Any] = urlopen,
    browser_opener: Callable[[str], bool] = webbrowser.open,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not stop_event.is_set() and time.monotonic() < deadline:
        try:
            with closing(health_opener(health_url, timeout=0.25)) as response:
                if response.status == 200:
                    if not browser_opener(launch_url):
                        _print_manual_launch_url(launch_url)
                    return
        except (OSError, URLError):
            pass
        stop_event.wait(0.05)

    if not stop_event.is_set():
        print(
            "bootAI could not confirm that the local web server was ready.",
            file=sys.stderr,
        )


def _print_manual_launch_url(launch_url: str) -> None:
    print("Open this temporary private URL in your browser:")
    print(launch_url)
    print("The URL works once and should not be shared.")
