from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROXY_CONFIG = ROOT / "management-proxy" / "nginx.conf"


def _allowed_management_request(*, method: str, path: str) -> bool:
    config = PROXY_CONFIG.read_text(encoding="utf-8")
    map_body = re.search(
        r'map "\$request_method:\$uri" \$management_route \{(?P<body>.*?)\n\s*\}',
        config,
        re.DOTALL,
    )
    assert map_body is not None

    request = f"{method}:{path}"
    patterns = re.findall(
        r"^\s*(\S+)\s+1;$",
        map_body.group("body"),
        re.MULTILINE,
    )
    for raw_pattern in patterns:
        if raw_pattern.startswith("~"):
            if re.fullmatch(raw_pattern[1:], request):
                return True
        elif raw_pattern.strip('"') == request:
            return True
    return False


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("GET", "/health", True),
        ("PUT", "/api/v1/profiles/42", True),
        ("DELETE", "/api/v1/profiles/42", True),
        ("POST", "/auth", False),
        ("GET", "/auth", False),
        ("POST", "/api/v1/profiles/42", False),
        ("GET", "/api/v1/profiles/42", False),
        ("GET", "/docs", False),
        ("GET", "/health/", False),
    ],
)
def test_proxy_allowlist_exposes_only_management_contract(
    method: str,
    path: str,
    allowed: bool,
) -> None:
    assert _allowed_management_request(method=method, path=path) is allowed


def test_proxy_denies_by_default_before_forwarding_to_internal_agent() -> None:
    config = PROXY_CONFIG.read_text(encoding="utf-8")

    assert "default 0;" in config
    assert "if ($management_route = 0)" in config
    assert "return 404;" in config
    assert config.count("proxy_pass") == 1
    assert "proxy_pass http://agent:8000;" in config


def test_proxy_runtime_files_use_the_writable_tmpfs() -> None:
    config = PROXY_CONFIG.read_text(encoding="utf-8")

    assert "pid /tmp/nginx.pid;" in config
    for directive in (
        "client_body_temp_path",
        "proxy_temp_path",
        "fastcgi_temp_path",
        "uwsgi_temp_path",
        "scgi_temp_path",
    ):
        assert re.search(rf"^\s*{directive} /tmp/", config, re.MULTILINE)
