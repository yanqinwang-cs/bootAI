from __future__ import annotations

import sys
from collections.abc import Sequence

_WEB_DEPENDENCY_MODULES = {
    "fastapi",
    "itsdangerous",
    "jinja2",
    "starlette",
    "uvicorn",
}


def main(argv: Sequence[str] | None = None) -> int:
    try:
        from organizer.web.server import main as server_main
    except ModuleNotFoundError as error:
        missing = (error.name or "").split(".", maxsplit=1)[0]
        if missing not in _WEB_DEPENDENCY_MODULES:
            raise
        print(
            "bootai[web] is not installed. "
            'Install it with: python -m pip install -e ".[web]"',
            file=sys.stderr,
        )
        return 2
    return server_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
