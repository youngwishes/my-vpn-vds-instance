from __future__ import annotations

import ipaddress
import json
import re
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _strings(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in _strings(nested)]
    return []


def test_xray_has_one_managed_vless_reality_inbound_and_private_api() -> None:
    config = json.loads((ROOT / "xray/config.json").read_text(encoding="utf-8"))

    assert config["api"] == {
        "tag": "api",
        "listen": "0.0.0.0:10085",
        "services": ["HandlerService"],
    }
    assert len(config["inbounds"]) == 1
    inbound = config["inbounds"][0]
    assert inbound["tag"] == "vless-reality"
    assert inbound["listen"] == "0.0.0.0"
    assert inbound["port"] == 443
    assert inbound["protocol"] == "vless"
    assert inbound["settings"] == {"clients": [], "decryption": "none"}
    assert inbound["streamSettings"]["network"] == "raw"
    assert inbound["streamSettings"]["security"] == "reality"
    assert inbound["streamSettings"]["realitySettings"] == {
        "show": False,
        "target": "__VPN_REALITY_TARGET__",
        "serverNames": ["__VPN_REALITY_SERVER_NAME__"],
        "privateKey": "__VPN_REALITY_PRIVATE_KEY__",
        "shortIds": ["__VPN_REALITY_SHORT_ID__"],
    }
    assert all("websocket" not in value.lower() for value in _strings(config))


def test_hysteria_has_one_udp_listener_local_http_auth_and_file_tls() -> None:
    config = json.loads((ROOT / "hysteria/config.yaml").read_text(encoding="utf-8"))

    assert config == {
        "listen": ":443",
        "tls": {
            "cert": "/run/secrets/hysteria_tls_cert",
            "key": "/run/secrets/hysteria_tls_key",
        },
        "auth": {
            "type": "http",
            "http": {"url": "http://agent:8000/auth"},
        },
        "obfs": {
            "type": "salamander",
            "salamander": {"password": "__VPN_HYSTERIA_OBFS__"},
        },
    }


def test_tracked_runtime_templates_contain_no_public_ip_or_secret_value() -> None:
    paths = [
        ROOT / ".env.example",
        ROOT / "docker-compose.yml",
        ROOT / "docker-compose.local.yml",
        ROOT / "xray/config.json",
        ROOT / "hysteria/config.yaml",
        ROOT / "deploy/inventory.example.ini",
        ROOT / "deploy/group_vars/vpn.example.yml",
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        for candidate in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", text):
            address = ipaddress.ip_address(candidate)
            assert not address.is_global, f"public address in {path}: {candidate}"

    xray = json.loads((ROOT / "xray/config.json").read_text(encoding="utf-8"))
    reality = xray["inbounds"][0]["streamSettings"]["realitySettings"]
    assert reality["privateKey"].startswith("__VPN_")
    assert reality["shortIds"][0].startswith("__VPN_")


def test_default_pytest_discovery_includes_deploy_contracts() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["tool"]["pytest"]["ini_options"]["testpaths"] == [
        "tests",
        "deploy/tests",
    ]
