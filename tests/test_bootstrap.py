from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
import respx

from src.backend.client import DjangoBackendClient
from src.domain.profiles import VPNProfile
from src.domain.store import InMemoryProfileStore
from src.services.bootstrap_service import BootstrapService, BootstrapState
from src.services.profile_service import ProfileService


class FakeXrayClient:
    def __init__(self) -> None:
        self.upserted: list[tuple[int, UUID]] = []

    def upsert_user(self, *, access_id: int, uuid: UUID) -> None:
        self.upserted.append((access_id, uuid))

    def delete_user(self, *, access_id: int) -> None:
        return None

    def health(self) -> None:
        return None


def test_backend_client_fetches_all_profiles_with_shared_bearer_token() -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://backend.example.test/api/v1/vpn/agent/profiles/").respond(
            200,
            json=[
                {
                    "access_id": 7,
                    "vless_uuid": "11111111-1111-1111-1111-111111111111",
                    "hysteria_secret": "hysteria-secret",
                }
            ],
        )
        profiles = asyncio.run(
            DjangoBackendClient(
                agent_token="shared-agent-token",
                backend_url="https://backend.example.test",
            ).fetch_profiles()
        )

    assert route.called
    assert route.calls[0].request.headers["Authorization"] == "Bearer shared-agent-token"
    assert profiles[0].access_id == 7


def test_bootstrap_marks_ready_only_after_all_profiles_are_applied() -> None:
    state = BootstrapState()
    store = InMemoryProfileStore()
    xray = FakeXrayClient()
    service = BootstrapService(
        backend_client=StaticBackendClient(),
        profile_service=ProfileService(profile_store=store, xray_client=xray),
        state=state,
        sleep=never_sleep,
    )

    asyncio.run(service())

    assert state.is_ready
    assert [access_id for access_id, _ in xray.upserted] == [7, 8]
    assert [profile.access_id for profile in store.get_all()] == [7, 8]


def test_bootstrap_stays_unhealthy_after_exactly_five_failed_attempts() -> None:
    state = BootstrapState()
    backend = FailingBackendClient()
    delays: list[float] = []
    service = BootstrapService(
        backend_client=backend,
        profile_service=ProfileService(
            profile_store=InMemoryProfileStore(),
            xray_client=FakeXrayClient(),
        ),
        state=state,
        sleep=lambda delay: record_sleep(delay=delay, delays=delays),
    )

    asyncio.run(service())

    assert backend.attempts == 5
    assert delays == [5, 5, 5, 5]
    assert not state.is_ready


class StaticBackendClient:
    async def fetch_profiles(self):
        return (
            VPNProfile(
                access_id=7,
                vless_uuid=UUID("11111111-1111-1111-1111-111111111111"),
                hysteria_secret="first-secret",
            ),
            VPNProfile(
                access_id=8,
                vless_uuid=UUID("22222222-2222-2222-2222-222222222222"),
                hysteria_secret="second-secret",
            ),
        )


class FailingBackendClient:
    def __init__(self) -> None:
        self.attempts = 0

    async def fetch_profiles(self):
        self.attempts += 1
        raise httpx.ConnectError("backend unavailable")


async def never_sleep(_: float) -> None:
    return None


async def record_sleep(*, delay: float, delays: list[float]) -> None:
    delays.append(delay)
