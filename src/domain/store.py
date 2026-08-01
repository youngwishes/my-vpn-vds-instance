from __future__ import annotations

from .profiles import VPNProfile


class InMemoryProfileStore:
    def __init__(self) -> None:
        self._profiles: dict[int, VPNProfile] = {}

    def get_all(self) -> tuple[VPNProfile, ...]:
        return tuple(self._profiles.values())

    def get_by_secret(self, *, secret: str) -> VPNProfile | None:
        return next(
            (profile for profile in self._profiles.values() if profile.hysteria_secret == secret),
            None,
        )

    def upsert(self, *, profile: VPNProfile) -> None:
        self._profiles[profile.access_id] = profile

    def delete(self, *, access_id: int) -> None:
        self._profiles.pop(access_id, None)
