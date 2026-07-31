from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Settings


AGENT_TOKEN = "test-management-token"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(settings=Settings(agent_token=AGENT_TOKEN))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {AGENT_TOKEN}"}
