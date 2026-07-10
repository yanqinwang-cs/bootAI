from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import secrets

from organizer.safety import validate_under_root

_MINIMUM_SECRET_LENGTH = 32
_LAUNCH_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,}")


def _session_secret() -> str:
    return secrets.token_urlsafe(48)


def _launch_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class WebAppConfig:
    root: Path
    session_secret: str = field(default_factory=_session_secret)
    launch_token: str = field(default_factory=_launch_token)
    testing: bool = False

    def __post_init__(self) -> None:
        resolved_root = self.root.expanduser().resolve()
        if not resolved_root.exists():
            raise ValueError(f"web root does not exist: {resolved_root}")
        if not resolved_root.is_dir():
            raise ValueError(f"web root is not a directory: {resolved_root}")
        object.__setattr__(
            self,
            "root",
            validate_under_root(resolved_root, resolved_root),
        )

        if (
            not isinstance(self.session_secret, str)
            or len(self.session_secret) < _MINIMUM_SECRET_LENGTH
        ):
            raise ValueError("session secret must contain at least 32 characters")
        if (
            not isinstance(self.launch_token, str)
            or _LAUNCH_TOKEN_PATTERN.fullmatch(self.launch_token) is None
        ):
            raise ValueError(
                "launch token must contain at least 32 URL-safe characters"
            )

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        if self.testing:
            return ("127.0.0.1", "localhost", "testserver")
        return ("127.0.0.1", "localhost")
