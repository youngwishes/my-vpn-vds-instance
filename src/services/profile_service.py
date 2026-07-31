from __future__ import annotations

from dataclasses import dataclass
from typing import final

from src.domain.profiles import VPNProfile
from src.domain.store import InMemoryProfileStore
from src.xray.service import XrayClient


@final
@dataclass(frozen=True, kw_only=True, slots=True)
class ProfileService:
    profile_store: InMemoryProfileStore
    xray_client: XrayClient

    def upsert(self, *, profile: VPNProfile) -> None:
        self.xray_client.upsert_user(
            access_id=profile.access_id,
            uuid=profile.vless_uuid,
        )
        self.profile_store.upsert(profile=profile)

    def delete(self, *, access_id: int) -> None:
        self.xray_client.delete_user(access_id=access_id)
        self.profile_store.delete(access_id=access_id)
