from __future__ import annotations

import logging

import pytest

from src.security.logging import RedactingFilter


def test_redacting_filter_removes_profile_and_bearer_secrets(caplog: pytest.LogCaptureFixture) -> None:
    secret = "hysteria-sensitive-secret"
    token = "agent-sensitive-token"
    logger = logging.getLogger("vpn-node-agent.test")
    logger.addFilter(RedactingFilter())

    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info(
            "profile={'hysteria_secret': '%s'} Authorization: Bearer %s",
            secret,
            token,
        )

    assert secret not in caplog.text
    assert token not in caplog.text
    assert "[REDACTED]" in caplog.text
