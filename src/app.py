from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api import health_router, management_router
from .config import Settings
from .domain.store import InMemoryProfileStore
from .factories import create_profile_store


def create_app(
    *,
    settings: Settings,
    profile_store: InMemoryProfileStore | None = None,
) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.state.profile_store = profile_store or create_profile_store()
    app.include_router(health_router)
    app.include_router(management_router)
    app.add_exception_handler(RequestValidationError, sanitized_validation_error)
    return app


async def sanitized_validation_error(
    _: Request,
    __: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Invalid request"})
