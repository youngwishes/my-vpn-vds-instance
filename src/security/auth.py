from __future__ import annotations

from hmac import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException, Request, status


def is_authorized(*, authorization: str | None, expected_token: str) -> bool:
    if authorization is None:
        return False

    scheme, _, token = authorization.partition(" ")
    return scheme == "Bearer" and bool(token) and compare_digest(token, expected_token)


async def require_management_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not is_authorized(
        authorization=authorization,
        expected_token=request.app.state.settings.agent_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
