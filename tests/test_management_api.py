from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_is_public_and_returns_exact_body(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_management_endpoints_require_bearer_auth(client: TestClient) -> None:
    response = client.put(
        "/api/v1/profiles/8",
        json={
            "vless_uuid": "11111111-1111-1111-1111-111111111111",
            "hysteria_secret": "never-return-this-secret",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_put_upserts_profile_idempotently_with_exact_response(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    body = {
        "vless_uuid": "11111111-1111-1111-1111-111111111111",
        "hysteria_secret": "never-return-this-secret",
    }

    first = client.put("/api/v1/profiles/8", headers=auth_headers, json=body)
    second = client.put("/api/v1/profiles/8", headers=auth_headers, json=body)

    assert first.status_code == 200
    assert first.json() == {"access_id": 8}
    assert second.status_code == 200
    assert second.json() == {"access_id": 8}


def test_put_validation_never_echoes_hysteria_secret(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    secret = "do-not-leak-validation-secret"
    response = client.put(
        "/api/v1/profiles/8",
        headers=auth_headers,
        json={"vless_uuid": "not-a-uuid", "hysteria_secret": secret},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
    assert secret not in response.text


def test_delete_is_idempotent_and_returns_no_body(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    first = client.delete("/api/v1/profiles/404", headers=auth_headers)
    second = client.delete("/api/v1/profiles/404", headers=auth_headers)

    assert first.status_code == 204
    assert first.content == b""
    assert second.status_code == 204
    assert second.content == b""
