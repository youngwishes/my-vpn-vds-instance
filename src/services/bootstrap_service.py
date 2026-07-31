from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import final

from src.backend.client import BackendClient

from .profile_service import ProfileService


@dataclass(slots=True)
class BootstrapState:
    is_ready: bool = False

    def mark_ready(self) -> None:
        self.is_ready = True


Sleep = Callable[[float], Awaitable[None]]


@final
@dataclass(frozen=True, kw_only=True, slots=True)
class BootstrapService:
    backend_client: BackendClient
    profile_service: ProfileService
    state: BootstrapState
    sleep: Sleep = asyncio.sleep

    async def __call__(self) -> None:
        for attempt in range(5):
            try:
                profiles = await self.backend_client.fetch_profiles()
                for profile in profiles:
                    self.profile_service.upsert(profile=profile)
            except Exception:
                if attempt < 4:
                    await self.sleep(5)
                continue

            self.state.mark_ready()
            return
