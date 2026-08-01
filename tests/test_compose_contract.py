from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APPROVED_PYTHON_VERSION = "3.13"
APPROVED_PYTHON_IMAGE = (
    "docker.io/library/python"
    "@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91"
)
APPROVED_XRAY_IMAGE = (
    "ghcr.io/xtls/xray-core"
    "@sha256:a1644183accdb0b5be967093fe34be756fd5de15fe2ee0206e842ae17350967f"
)
APPROVED_MANAGEMENT_PROXY_IMAGE = (
    "ghcr.io/nginx/nginx-unprivileged"
    "@sha256:8122337ed6c475bb486bc9340da453d4599f225e6b920ff0d92ca2267486b9b5"
)
IMAGE_BY_SERVICE = {
    "hysteria": "docker.io/tobyxdd/hysteria",
}


def test_python_toolchain_and_runtime_match_approved_version() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == (
        APPROVED_PYTHON_VERSION
    )
    assert project["project"]["requires-python"] == f">={APPROVED_PYTHON_VERSION}"
    assert lock["requires-python"] == project["project"]["requires-python"]
    assert f"FROM {APPROVED_PYTHON_IMAGE} AS agent" in dockerfile


def _compose_config(*, environment: dict[str, str] | None = None) -> dict[str, Any]:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **(environment or {})},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_runtime_images_are_immutable_and_agent_uses_the_same_xray_binary() -> None:
    config = _compose_config()

    assert config["services"]["xray"]["image"] == APPROVED_XRAY_IMAGE
    assert (
        config["services"]["management-proxy"]["image"]
        == APPROVED_MANAGEMENT_PROXY_IMAGE
    )
    for service_name, repository in IMAGE_BY_SERVICE.items():
        image = config["services"][service_name]["image"]
        assert re.fullmatch(rf"{re.escape(repository)}@sha256:[0-9a-f]{{64}}", image)

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    xray_image = config["services"]["xray"]["image"]
    assert f"FROM {xray_image} AS xray" in dockerfile
    assert "COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray" in dockerfile


def test_docker_build_context_excludes_local_credentials_and_caches() -> None:
    ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {
        ".git",
        ".venv",
        "**/__pycache__",
        ".pytest_cache",
        ".env",
        "secrets",
        ".superpowers",
    } <= ignored


def test_only_proxy_publishes_loopback_management_and_agent_stays_internal() -> None:
    config = _compose_config()
    published_ports = {
        (
            service_name,
            port["target"],
            port["published"],
            port["protocol"],
            port.get("host_ip", ""),
        )
        for service_name, service in config["services"].items()
        for port in service.get("ports", [])
    }

    assert published_ports == {
        ("management-proxy", 8080, "8443", "tcp", "127.0.0.1"),
        ("xray", 443, "443", "tcp", "0.0.0.0"),
        ("hysteria", 443, "443", "udp", "0.0.0.0"),
    }
    assert config["services"]["agent"].get("ports", []) == []


def test_management_listener_can_bind_to_an_explicit_public_address() -> None:
    config = _compose_config(
        environment={"VPN_AGENT_BIND_ADDRESS": "203.0.113.10"}
    )
    management_port = next(
        port
        for port in config["services"]["management-proxy"]["ports"]
        if port["target"] == 8080
    )

    assert management_port["host_ip"] == "203.0.113.10"
    assert management_port["published"] == "8443"


def test_control_endpoints_and_secret_files_stay_on_the_internal_network() -> None:
    config = _compose_config()
    services = config["services"]

    assert config["networks"]["control"]["internal"] is True
    assert set(services["agent"]["networks"]) == {"control", "agent_egress"}
    assert set(services["management-proxy"]["networks"]) == {"control"}
    assert set(services["xray"]["networks"]) == {"control", "xray_egress"}
    assert set(services["hysteria"]["networks"]) == {
        "control",
        "hysteria_egress",
    }

    secret_targets = {
        service_name: {
            secret["source"]: f"/run/secrets/{secret['target']}"
            for secret in service.get("secrets", [])
        }
        for service_name, service in services.items()
    }
    assert secret_targets == {
        "agent": {"vpn_agent_token": "/run/secrets/vpn_agent_token"},
        "management-proxy": {},
        "xray": {"xray_config": "/run/secrets/xray_config"},
        "hysteria": {
            "hysteria_config": "/run/secrets/hysteria_config",
            "hysteria_tls_cert": "/run/secrets/hysteria_tls_cert",
            "hysteria_tls_key": "/run/secrets/hysteria_tls_key",
        },
    }
    assert "VPN_AGENT_TOKEN" not in services["agent"].get("environment", {})
    assert services["management-proxy"].get("secrets", []) == []


def test_local_override_keeps_agent_internal_and_publishes_only_proxy() -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.local.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)

    assert config["services"]["agent"].get("ports", []) == []
    assert config["services"]["management-proxy"]["ports"] == [
        {
            "mode": "ingress",
            "target": 8080,
            "published": "18000",
            "protocol": "tcp",
            "host_ip": "127.0.0.1",
        }
    ]
