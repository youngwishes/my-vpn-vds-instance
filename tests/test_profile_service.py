from __future__ import annotations

from uuid import UUID

import pytest

from src.domain.profiles import VPNProfile
from src.domain.store import InMemoryProfileStore
from src.services.profile_service import ProfileService
from src.xray.client import HandlerServiceXrayClient


class FakeXrayClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.upserted: list[tuple[int, UUID]] = []
        self.deleted: list[int] = []

    def upsert_user(self, *, access_id: int, uuid: UUID) -> None:
        if self.error is not None:
            raise self.error
        self.upserted.append((access_id, uuid))

    def delete_user(self, *, access_id: int) -> None:
        if self.error is not None:
            raise self.error
        self.deleted.append(access_id)

    def health(self) -> None:
        return None


def test_upsert_publishes_profile_only_after_xray_succeeds() -> None:
    store = InMemoryProfileStore()
    xray = FakeXrayClient()
    profile = VPNProfile(
        access_id=17,
        vless_uuid=UUID("11111111-1111-1111-1111-111111111111"),
        hysteria_secret="hysteria-secret",
    )

    ProfileService(profile_store=store, xray_client=xray).upsert(profile=profile)

    assert xray.upserted == [(17, profile.vless_uuid)]
    assert store.get_all() == (profile,)


def test_upsert_does_not_publish_profile_when_xray_fails() -> None:
    store = InMemoryProfileStore()
    profile = VPNProfile(
        access_id=17,
        vless_uuid=UUID("11111111-1111-1111-1111-111111111111"),
        hysteria_secret="hysteria-secret",
    )

    with pytest.raises(RuntimeError, match="xray unavailable"):
        ProfileService(
            profile_store=store,
            xray_client=FakeXrayClient(error=RuntimeError("xray unavailable")),
        ).upsert(profile=profile)

    assert store.get_all() == ()


def test_upsert_does_not_publish_profile_when_xray_added_zero_users() -> None:
    store = InMemoryProfileStore()
    profile = VPNProfile(
        access_id=17,
        vless_uuid=UUID("11111111-1111-1111-1111-111111111111"),
        hysteria_secret="hysteria-secret",
    )

    with pytest.raises(RuntimeError, match="Xray did not add user"):
        ProfileService(
            profile_store=store,
            xray_client=FakeXrayClient(error=RuntimeError("Xray did not add user")),
        ).upsert(profile=profile)

    assert store.get_all() == ()


def test_delete_removes_xray_user_before_in_memory_profile_and_is_idempotent() -> None:
    store = InMemoryProfileStore()
    profile = VPNProfile(
        access_id=17,
        vless_uuid=UUID("11111111-1111-1111-1111-111111111111"),
        hysteria_secret="hysteria-secret",
    )
    store.upsert(profile=profile)
    xray = FakeXrayClient()
    service = ProfileService(profile_store=store, xray_client=xray)

    service.delete(access_id=17)
    service.delete(access_id=17)

    assert xray.deleted == [17, 17]
    assert store.get_all() == ()


def test_delete_keeps_in_memory_profile_when_xray_remove_is_unconfirmed() -> None:
    store = InMemoryProfileStore()
    profile = VPNProfile(
        access_id=17,
        vless_uuid=UUID("11111111-1111-1111-1111-111111111111"),
        hysteria_secret="hysteria-secret",
    )
    store.upsert(profile=profile)
    service = ProfileService(
        profile_store=store,
        xray_client=HandlerServiceXrayClient(
            api_address="127.0.0.1:10085",
            inbound_tag="vless-reality",
            command_runner=lambda _: "rpc error: unavailable\nRemoved 0 user(s) in total.\n",
        ),
    )

    with pytest.raises(RuntimeError, match="Xray did not remove user"):
        service.delete(access_id=17)

    assert store.get_all() == (profile,)
