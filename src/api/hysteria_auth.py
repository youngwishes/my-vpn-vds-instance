from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel


router = APIRouter()


class HysteriaAuthRequest(BaseModel):
    addr: str
    auth: str
    tx: int


@router.post("/auth")
async def authenticate_hysteria(
    auth_request: HysteriaAuthRequest,
    request: Request,
) -> dict[str, bool | str]:
    profile = request.app.state.profile_store.get_by_secret(secret=auth_request.auth)
    if profile is None:
        return {"ok": False, "id": ""}
    return {"ok": True, "id": str(profile.access_id)}
