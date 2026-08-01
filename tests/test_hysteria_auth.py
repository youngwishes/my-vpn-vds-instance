from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Settings
from src.domain.profiles import VPNProfile
from src.domain.store import InMemoryProfileStore


def test_hysteria_auth_returns_official_response_for_known_credential() -> None:
    store = InMemoryProfileStore()
    store.upsert(
        profile=VPNProfile(
            access_id=12,
            vless_uuid=UUID("11111111-1111-1111-1111-111111111111"),
            hysteria_secret="valid-secret",
        )
    )
    app = create_app(
        settings=Settings(agent_token="agent-token"),
        profile_store=store,
    )

    with TestClient(app) as client:
        response = client.post(
            "/auth",
            json={"addr": "192.0.2.10:443", "auth": "valid-secret", "tx": 1234},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "id": "12"}


def test_hysteria_auth_rejects_unknown_credential_with_http_200() -> None:
    app = create_app(settings=Settings(agent_token="agent-token"))

    with TestClient(app) as client:
        response = client.post(
            "/auth",
            json={"addr": "192.0.2.10:443", "auth": "unknown", "tx": 1234},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": False, "id": ""}
