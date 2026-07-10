"""Local web interface package.

The package root remains importable without the optional web dependencies so
the core CLI is unaffected. Import ``organizer.web.app`` to construct an app.
"""

from organizer.web.config import WebAppConfig

__all__ = ["WebAppConfig"]
