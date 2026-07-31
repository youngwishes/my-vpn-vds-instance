from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator, Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api import health_router, hysteria_auth_router, management_router
from .config import Settings
from .domain.store import InMemoryProfileStore
from .factories import (
    create_bootstrap_service,
    create_profile_service,
    create_profile_store,
    create_xray_client,
)
from .services.bootstrap_service import BootstrapState
from .services.profile_service import ProfileService
from .xray.service import XrayClient


class BootstrapTask(Protocol):
    state: BootstrapState

    async def __call__(self) -> None: ...


def create_app(
    *,
    settings: Settings,
    profile_store: InMemoryProfileStore | None = None,
    xray_client: XrayClient | None = None,
    profile_service: ProfileService | None = None,
    bootstrap_service: BootstrapTask | None = None,
) -> FastAPI:
    store = profile_store or create_profile_store()
    xray = xray_client or create_xray_client(settings=settings)
    service = profile_service or create_profile_service(
        profile_store=store,
        xray_client=xray,
    )
    bootstrap = bootstrap_service or create_bootstrap_service(
        settings=settings,
        profile_service=service,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(bootstrap())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.state.profile_store = store
    app.state.xray_client = xray
    app.state.profile_service = service
    app.state.bootstrap_service = bootstrap
    app.include_router(health_router)
    app.include_router(hysteria_auth_router)
    app.include_router(management_router)
    app.add_exception_handler(RequestValidationError, sanitized_validation_error)
    return app


async def sanitized_validation_error(
    _: Request,
    __: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Invalid request"})
