from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from organizer.web.config import WebAppConfig
from organizer.web.routes.home import create_home_router
from organizer.web.routes.consumer import create_consumer_router
from organizer.web.routes.review import create_review_router
from organizer.web.review_explorer import ReviewExplorerStore
from organizer.web.scan_jobs import ScanJobController
from organizer.web.security import (
    LaunchTokenGate,
    SecurityHeadersMiddleware,
    apply_security_headers,
)

_PACKAGE_DIRECTORY = Path(__file__).resolve().parent
_TEMPLATE_DIRECTORY = _PACKAGE_DIRECTORY / "templates"
_STATIC_DIRECTORY = _PACKAGE_DIRECTORY / "static"


def create_app(config: WebAppConfig) -> FastAPI:
    templates = Jinja2Templates(directory=str(_TEMPLATE_DIRECTORY))
    middleware = [
        Middleware(SecurityHeadersMiddleware),
        Middleware(
            TrustedHostMiddleware,
            allowed_hosts=list(config.allowed_hosts),
            www_redirect=False,
        ),
        Middleware(
            SessionMiddleware,
            secret_key=config.session_secret,
            session_cookie="bootai_session",
            max_age=None,
            path="/",
            same_site="strict",
            https_only=False,
        ),
    ]
    app = FastAPI(
        debug=False,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        middleware=middleware,
    )
    app.state.web_config = config
    app.state.templates = templates
    app.state.launch_token_gate = LaunchTokenGate(config.launch_token)
    app.state.scan_jobs = ScanJobController(config.root)
    app.state.review_explorer = ReviewExplorerStore(config.root)
    app.include_router(create_home_router(templates))
    app.include_router(create_consumer_router(templates))
    app.include_router(create_review_router(templates))
    app.mount(
        "/static",
        StaticFiles(directory=str(_STATIC_DIRECTORY), check_dir=True),
        name="static",
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(
        request: Request,
        error: StarletteHTTPException,
    ) -> Response:
        if error.status_code == 404:
            heading = "Page unavailable"
            message = "This bootAI page is not available."
        else:
            heading = "Request unavailable"
            message = "This bootAI request is not available."
        response = templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "page_title": heading,
                "heading": heading,
                "message": message,
            },
            status_code=error.status_code,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> Response:
        del error
        response = templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "page_title": "Session unavailable",
                "heading": "Session unavailable",
                "message": (
                    "This bootAI session is not available. "
                    "Launch bootAI again from the local application."
                ),
            },
            status_code=500,
        )
        response.headers["Cache-Control"] = "no-store"
        return apply_security_headers(response)

    return app
