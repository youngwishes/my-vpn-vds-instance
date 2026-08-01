from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Settings
from src.services.bootstrap_service import BootstrapState


class WaitingBootstrapService:
    def __init__(self, state: BootstrapState) -> None:
        self.state = state
        self.release = asyncio.Event()

    async def __call__(self) -> None:
        await self.release.wait()


class FakeXrayClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    def health(self) -> None:
        if self.error is not None:
            raise self.error


def test_health_is_unhealthy_until_background_bootstrap_completes() -> None:
    bootstrap = WaitingBootstrapService(state=BootstrapState())
    app = create_app(
        settings=Settings(agent_token="agent-token"),
        bootstrap_service=bootstrap,
        xray_client=FakeXrayClient(),
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy"}


def test_ready_health_turns_unhealthy_when_xray_check_fails() -> None:
    state = BootstrapState()
    state.mark_ready()
    bootstrap = WaitingBootstrapService(state=state)
    app = create_app(
        settings=Settings(agent_token="agent-token"),
        bootstrap_service=bootstrap,
        xray_client=FakeXrayClient(error=RuntimeError("xray unavailable")),
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy"}
