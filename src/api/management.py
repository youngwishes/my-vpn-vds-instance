from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from src.domain.profiles import VPNProfile
from src.security.auth import require_management_auth


router = APIRouter(
    prefix="/api/v1/profiles",
    dependencies=[Depends(require_management_auth)],
)


class ProfileUpsertRequest(BaseModel):
    vless_uuid: UUID
    hysteria_secret: Annotated[str, Field(min_length=1)]


@router.put("/{access_id}")
async def upsert_profile(
    access_id: int,
    profile_request: ProfileUpsertRequest,
    request: Request,
) -> dict[str, int]:
    request.app.state.profile_store.upsert(
        profile=VPNProfile(
            access_id=access_id,
            vless_uuid=profile_request.vless_uuid,
            hysteria_secret=profile_request.hysteria_secret,
        )
    )
    return {"access_id": access_id}


@router.delete("/{access_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(access_id: int, request: Request) -> Response:
    request.app.state.profile_store.delete(access_id=access_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
