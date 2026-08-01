from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Settings
from src.services.bootstrap_service import BootstrapState


AGENT_TOKEN = "test-management-token"


class FakeXrayClient:
    def upsert_user(self, **_: object) -> None:
        return None

    def delete_user(self, **_: object) -> None:
        return None

    def health(self) -> None:
        return None


class ReadyBootstrapService:
    def __init__(self) -> None:
        self.state = BootstrapState()
        self.state.mark_ready()

    async def __call__(self) -> None:
        return None


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(
        settings=Settings(agent_token=AGENT_TOKEN),
        xray_client=FakeXrayClient(),
        bootstrap_service=ReadyBootstrapService(),
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {AGENT_TOKEN}"}
