from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APPROVED_XRAY_IMAGE = (
    "ghcr.io/xtls/xray-core"
    "@sha256:a1644183accdb0b5be967093fe34be756fd5de15fe2ee0206e842ae17350967f"
)
IMAGE_BY_SERVICE = {
    "hysteria": "docker.io/tobyxdd/hysteria",
}


def _compose_config() -> dict[str, Any]:
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
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_runtime_images_are_immutable_and_agent_uses_the_same_xray_binary() -> None:
    config = _compose_config()

    assert config["services"]["xray"]["image"] == APPROVED_XRAY_IMAGE
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


def test_only_vpn_listeners_are_public_and_management_is_loopback_only() -> None:
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
        ("agent", 8000, "8443", "tcp", "127.0.0.1"),
        ("xray", 443, "443", "tcp", "0.0.0.0"),
        ("hysteria", 443, "443", "udp", "0.0.0.0"),
    }


def test_control_endpoints_and_secret_files_stay_on_the_internal_network() -> None:
    config = _compose_config()
    services = config["services"]

    assert config["networks"]["control"]["internal"] is True
    assert set(services["agent"]["networks"]) == {"control", "agent_egress"}
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
        "xray": {"xray_config": "/run/secrets/xray_config"},
        "hysteria": {
            "hysteria_config": "/run/secrets/hysteria_config",
            "hysteria_tls_cert": "/run/secrets/hysteria_tls_cert",
            "hysteria_tls_key": "/run/secrets/hysteria_tls_key",
        },
    }
    assert "VPN_AGENT_TOKEN" not in services["agent"].get("environment", {})
