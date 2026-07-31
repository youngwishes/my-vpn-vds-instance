from __future__ import annotations

from uuid import UUID

from src.domain.profiles import VPNProfile
from src.domain.store import InMemoryProfileStore


def test_store_upsert_replaces_profile_by_access_id() -> None:
    store = InMemoryProfileStore()
    original = VPNProfile(
        access_id=12,
        vless_uuid=UUID("11111111-1111-1111-1111-111111111111"),
        hysteria_secret="first-secret",
    )
    replacement = VPNProfile(
        access_id=12,
        vless_uuid=UUID("22222222-2222-2222-2222-222222222222"),
        hysteria_secret="second-secret",
    )

    store.upsert(profile=original)
    store.upsert(profile=replacement)

    assert store.get_all() == (replacement,)
    assert store.get_by_secret(secret="first-secret") is None
    assert store.get_by_secret(secret="second-secret") == replacement


def test_store_delete_is_idempotent() -> None:
    store = InMemoryProfileStore()

    store.delete(access_id=999)

    assert store.get_all() == ()
