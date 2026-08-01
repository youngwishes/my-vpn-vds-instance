from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, final

import httpx

from src.domain.profiles import VPNProfile


class BackendClient(Protocol):
    async def fetch_profiles(self) -> Sequence[VPNProfile]: ...


@final
@dataclass(frozen=True, kw_only=True, slots=True)
class DjangoBackendClient:
    backend_url: str
    agent_token: str

    async def fetch_profiles(self) -> tuple[VPNProfile, ...]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.backend_url.rstrip('/')}/api/v1/vpn/agent/profiles/",
                headers={"Authorization": f"Bearer {self.agent_token}"},
            )
        response.raise_for_status()
        return tuple(VPNProfile(**profile) for profile in response.json())
