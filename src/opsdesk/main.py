from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from opsdesk.admin.api import router as admin_api_router
from opsdesk.admin.web import router as admin_web_router
from opsdesk.api.errors import OPENAPI_ERROR_RESPONSES, register_exception_handlers
from opsdesk.api.system import router as system_router
from opsdesk.auth.api import router as auth_api_router
from opsdesk.auth.web import router as auth_web_router
from opsdesk.categories.api import router as category_api_router
from opsdesk.core.config import Settings, get_settings
from opsdesk.db.session import get_engine
from opsdesk.observability.logging import configure_logging, get_logger
from opsdesk.observability.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from opsdesk.tickets.api import dashboard_router
from opsdesk.tickets.api import router as ticket_api_router
from opsdesk.tickets.web import router as ticket_web_router
from opsdesk.users.api import router as user_api_router


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    configure_logging(active_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        get_logger().info("application.started", event_name="application.started")
        yield
        get_engine().dispose()

    app = FastAPI(
        title="OpsDesk",
        description="Support ticket and knowledge management application",
        version=active_settings.version,
        lifespan=lifespan,
        responses=OPENAPI_ERROR_RESPONSES,
    )
    app.state.settings = active_settings
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware, settings=active_settings)
    register_exception_handlers(app)
    app.include_router(system_router)
    app.include_router(auth_api_router)
    app.include_router(category_api_router)
    app.include_router(ticket_api_router)
    app.include_router(dashboard_router)
    app.include_router(user_api_router)
    app.include_router(admin_api_router)
    app.include_router(auth_web_router)
    app.include_router(ticket_web_router)
    app.include_router(admin_web_router)
    static_path = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    return app


app = create_app()
