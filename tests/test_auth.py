from __future__ import annotations

from src.security.auth import is_authorized


def test_bearer_auth_accepts_only_the_configured_token() -> None:
    assert is_authorized(
        authorization="Bearer configured-token",
        expected_token="configured-token",
    )
    assert not is_authorized(
        authorization="Bearer another-token",
        expected_token="configured-token",
    )
    assert not is_authorized(
        authorization="Basic configured-token",
        expected_token="configured-token",
    )
    assert not is_authorized(authorization=None, expected_token="configured-token")
