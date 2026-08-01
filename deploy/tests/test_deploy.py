from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_playbook_is_valid_and_deploys_an_explicit_git_revision() -> None:
    result = subprocess.run(
        [
            "ansible-playbook",
            "--syntax-check",
            "-i",
            "deploy/inventory.example.ini",
            "deploy/playbook.yml",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")
    assert 'version: "{{ deploy_revision }}"' in playbook
    assert "docker compose pull" in playbook
    assert "docker compose build --pull agent" in playbook
    assert "docker compose up -d --remove-orphans" in playbook
    assert "docker compose down" not in playbook


def test_deploy_renders_read_only_secrets_without_logging_them() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")

    for secret_name in (
        "vpn_agent_token",
        "vpn_reality_private_key",
        "vpn_hysteria_tls_cert",
        "vpn_hysteria_tls_key",
    ):
        assert secret_name in playbook
        assert f"- {secret_name} | length > 0" in playbook
    assert "- vpn_hysteria_obfs | length > 0" in playbook
    assert playbook.count("no_log: true") >= 2
    assert 'mode: "0400"' in playbook


def test_deploy_renders_templates_from_the_checked_out_revision() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")

    xray_source = 'src: "{{ vpn_deploy_root_effective }}/xray/config.json"'
    hysteria_source = 'src: "{{ vpn_deploy_root_effective }}/hysteria/config.yaml"'
    assert xray_source in playbook
    assert hysteria_source in playbook

    checkout = playbook.index("Check out the requested immutable revision")
    xray_slurp = playbook.index(xray_source)
    hysteria_slurp = playbook.index(hysteria_source)
    render = playbook.index("Render runtime secret files")

    assert checkout < xray_slurp < render
    assert checkout < hysteria_slurp < render
    assert "xray_template.content | b64decode" in playbook
    assert "hysteria_template.content | b64decode" in playbook
    assert "lookup('ansible.builtin.file'" not in playbook


def test_deploy_uses_management_proxy_config_from_checked_out_revision() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "Check out the requested immutable revision" in playbook
    assert "docker compose up -d --remove-orphans" in playbook
    assert "./management-proxy/nginx.conf:/etc/nginx/nginx.conf:ro" in compose


def test_example_inventory_and_vars_have_no_server_ip_or_credentials() -> None:
    inventory = (ROOT / "deploy/inventory.example.ini").read_text(encoding="utf-8")
    variables = (ROOT / "deploy/group_vars/vpn.example.yml").read_text(
        encoding="utf-8"
    )

    assert "example.invalid" in inventory
    assert re.search(r"(?:\d{1,3}\.){3}\d{1,3}", inventory) is None
    for secret_name in (
        "vpn_agent_token",
        "vpn_reality_private_key",
        "vpn_hysteria_tls_cert",
        "vpn_hysteria_tls_key",
    ):
        assert re.search(rf"^{secret_name}\s*:", variables, re.MULTILINE) is None

    assert 'vpn_agent_bind_address: ""' in variables
    assert 'vpn_backend_source_cidr: ""' in variables


def test_deploy_restricts_private_management_route_in_docker_user() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")

    assert "ipaddress.ip_address" in playbook
    assert "ipaddress.ip_network" in playbook
    assert "vpn_agent_bind_address" in playbook
    assert "vpn_backend_source_cidr" in playbook
    assert "VPN_AGENT_BIND_ADDRESS={{ vpn_agent_bind_address }}" in playbook

    allow = (
        "iptables -A VPN_AGENT_MGMT -p tcp -s {{ vpn_backend_source_cidr }} "
        "-m conntrack --ctdir ORIGINAL --ctorigdst {{ vpn_agent_bind_address }} "
        "--ctorigdstport {{ vpn_management_port | default(8443) }} -j ACCEPT"
    )
    deny = (
        "iptables -A VPN_AGENT_MGMT -p tcp -m conntrack "
        "--ctdir ORIGINAL --ctorigdst {{ vpn_agent_bind_address }} "
        "--ctorigdstport {{ vpn_management_port | default(8443) }} -j DROP"
    )
    assert allow in playbook
    assert deny in playbook
    assert playbook.index(allow) < playbook.index(deny)
    assert "iptables -C DOCKER-USER -j VPN_AGENT_MGMT" in playbook
    assert "iptables -I DOCKER-USER 1 -j VPN_AGENT_MGMT" in playbook
    assert "After=docker.service" in playbook
    assert "enabled: true" in playbook
