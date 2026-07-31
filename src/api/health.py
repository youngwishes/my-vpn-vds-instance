from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


router = APIRouter()


@router.get("/health", response_model=None)
async def health(request: Request) -> dict[str, str] | JSONResponse:
    if not request.app.state.bootstrap_service.state.is_ready:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})

    try:
        request.app.state.xray_client.health()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})

    return {"status": "ok"}
