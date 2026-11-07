from __future__ import annotations

import json
import os
import re
import signal
import stat
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run_script(
    script: Path,
    *,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )


def test_playbook_is_valid_and_deploys_main_from_github() -> None:
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
    assert "https://github.com/youngwishes/my-vpn-vds-instance.git" in playbook
    assert 'version: "{{ vpn_repository_version }}"' in playbook
    assert "vpn_repository_version: main" in playbook
    assert "deploy_revision" not in playbook
    assert "docker compose pull" in playbook
    assert "docker compose build --pull agent" in playbook
    assert "docker compose up -d --remove-orphans" in playbook
    assert "docker compose down" not in playbook


def test_playbook_defaults_reality_to_the_live_com_domain() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")

    assert "vpn_reality_target | default('mtprotokeys.com:443')" in playbook
    assert "vpn_reality_server_name | default('mtprotokeys.com')" in playbook


def test_playbook_preserves_an_existing_docker_compose_installation() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")

    base_packages = playbook[
        playbook.index("Install Git, OpenSSL and Certbot") :
        playbook.index("Check whether Docker engine is available")
    ]
    assert "docker.io" not in base_packages
    assert "docker-compose-v2" not in base_packages

    engine_probe = playbook[
        playbook.index("Check whether Docker engine is available") :
        playbook.index("Install Docker engine when unavailable")
    ]
    assert "docker --version" in engine_probe
    assert "failed_when: false" in engine_probe
    assert "register: vpn_docker_engine_check" in engine_probe

    docker_install = playbook[
        playbook.index("Install Docker engine when unavailable") :
        playbook.index("Check whether Docker Compose is available")
    ]
    assert "docker.io" in docker_install
    assert "docker-compose-v2" not in docker_install
    assert "when: vpn_docker_engine_check.rc != 0" in docker_install

    compose_probe = playbook[
        playbook.index("Check whether Docker Compose is available") :
        playbook.index("Install Docker Compose when unavailable")
    ]
    assert "docker compose version" in compose_probe
    assert "failed_when: false" in compose_probe
    assert "register: vpn_docker_compose_check" in compose_probe

    compose_install = playbook[
        playbook.index("Install Docker Compose when unavailable") :
        playbook.index("Ensure Docker is running")
    ]
    assert "docker.io" not in compose_install
    assert "docker-compose-v2" in compose_install
    assert "when: vpn_docker_compose_check.rc != 0" in compose_install


def test_playbook_creates_persistent_swap_only_when_no_swap_is_active() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")

    assert "vpn_swap_size_mb_effective" in playbook
    assert "vpn_swap_size_mb | default(2048)" in playbook

    swap_tasks = playbook[
        playbook.index("Configure swap when none is active") :
        playbook.index("Check whether Docker Compose is available")
    ]
    assert "ansible_swaptotal_mb | int == 0" in swap_tasks
    assert "fallocate" in swap_tasks
    assert 'mode: "0600"' in swap_tasks
    assert "mkswap" in swap_tasks
    assert "/swapfile none swap sw 0 0" in swap_tasks
    assert "swapon /swapfile" in swap_tasks
    assert swap_tasks.index("Activate the swap file") < swap_tasks.index(
        "Persist the swap file"
    )
    assert "swapon --show=NAME --noheadings --raw" in swap_tasks
    assert "register: vpn_active_swap_paths" in swap_tasks
    persist_tasks = swap_tasks[
        swap_tasks.index("Persist the swap file") :
    ]
    assert "- ansible_swaptotal_mb | int == 0" in persist_tasks
    assert (
        "- \"'/swapfile' in vpn_active_swap_paths.stdout_lines\""
        in persist_tasks
    )
    assert "Refuse to overwrite a non-swap /swapfile" in swap_tasks
    assert "vpn_swapfile_stat.stat.isreg" in swap_tasks
    assert "vpn_swapfile_stat.stat.islnk" in swap_tasks

    staging_tasks = swap_tasks[
        swap_tasks.index("Prepare a new swap file") :
        swap_tasks.index("Restrict swap file permissions")
    ]
    assert "ansible.builtin.tempfile" in staging_tasks
    assert "prefix: .vpn-node-swapfile." in staging_tasks
    assert "register: vpn_swapfile_staging" in staging_tasks
    assert "vpn_swapfile_staging.path" in staging_tasks
    assert "always:" in staging_tasks
    assert staging_tasks.index("mkswap") < staging_tasks.index("- ln")
    assert staging_tasks.index("- ln") < staging_tasks.index("- -T")
    assert staging_tasks.index("- ln") < staging_tasks.index("- /swapfile")


def test_node_secret_generator_creates_once_and_preserves_existing_material(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'PrivateKey: private-first' "
        "'Password (PublicKey): public-first' 'Hash32: ignored'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    openssl = bin_dir / "openssl"
    openssl.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  'rand -hex 8') printf '%s\\n' '0011223344556677' ;;\n"
        "  'rand -hex 32') printf '%s\\n' "
        "'0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef' ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    openssl.chmod(0o755)
    secrets_dir = tmp_path / "secrets"
    script = ROOT / "deploy/files/generate-node-secrets"
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "VPN_SECRETS_DIR": str(secrets_dir),
        "XRAY_IMAGE": "example.invalid/xray@sha256:test",
    }

    first = _run_script(script, env=env)

    assert first.returncode == 0, first.stderr
    state_path = secrets_dir / "node-secrets.json"
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "hysteria_obfs": (
            "0123456789abcdef0123456789abcdef"
            "0123456789abcdef0123456789abcdef"
        ),
        "reality_private_key": "private-first",
        "reality_public_key": "public-first",
        "reality_short_id": "0011223344556677",
    }
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600

    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'PrivateKey: private-second' "
        "'Password (PublicKey): public-second'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    second = _run_script(script, env=env)

    assert second.returncode == 0, second.stderr
    assert json.loads(state_path.read_text(encoding="utf-8"))[
        "reality_private_key"
    ] == "private-first"


def test_node_secret_generator_adopts_complete_legacy_runtime(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "xray-config.json").write_text(
        json.dumps(
            {
                "inbounds": [
                    {
                        "tag": "vless-reality",
                        "protocol": "vless",
                        "streamSettings": {
                            "security": "reality",
                            "realitySettings": {
                                "privateKey": "legacy-private",
                                "shortIds": ["aabb"],
                            }
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (secrets_dir / "hysteria-config.yaml").write_text(
        json.dumps(
            {
                "obfs": {
                    "type": "salamander",
                    "salamander": {"password": "short obfs"},
                }
            }
        ),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker.log"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" > \"$DOCKER_LOG\"\n"
        "printf '%s\\n' 'Password (PublicKey): legacy-public' 'Hash32: ignored'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    openssl = bin_dir / "openssl"
    openssl.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    openssl.chmod(0o755)

    result = _run_script(
        ROOT / "deploy/files/generate-node-secrets",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "VPN_SECRETS_DIR": str(secrets_dir),
            "XRAY_IMAGE": "example.invalid/xray@sha256:test",
            "DOCKER_LOG": str(docker_log),
        },
    )

    assert result.returncode == 0, result.stderr
    state_path = secrets_dir / "node-secrets.json"
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "hysteria_obfs": "short obfs",
        "reality_private_key": "legacy-private",
        "reality_public_key": "legacy-public",
        "reality_short_id": "aabb",
    }
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert docker_log.read_text(encoding="utf-8") == (
        "run --rm example.invalid/xray@sha256:test "
        "x25519 -i legacy-private\n"
    )


def test_node_secret_generator_rejects_partial_legacy_runtime(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "xray-config.json").write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'PrivateKey: unexpected-private' "
        "'Password (PublicKey): unexpected-public'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    openssl = bin_dir / "openssl"
    openssl.write_text(
        "#!/bin/sh\nprintf '%s\\n' '0011223344556677'\n",
        encoding="utf-8",
    )
    openssl.chmod(0o755)

    result = _run_script(
        ROOT / "deploy/files/generate-node-secrets",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "VPN_SECRETS_DIR": str(secrets_dir),
            "XRAY_IMAGE": "example.invalid/xray@sha256:test",
        },
    )

    assert result.returncode != 0
    assert not (secrets_dir / "node-secrets.json").exists()


def test_node_secret_generator_rejects_inactive_salamander_legacy_config(
    tmp_path: Path,
) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "xray-config.json").write_text(
        json.dumps(
            {
                "inbounds": [
                    {
                        "tag": "vless-reality",
                        "protocol": "vless",
                        "streamSettings": {
                            "security": "reality",
                            "realitySettings": {
                                "privateKey": "legacy-private",
                                "shortIds": ["aabb"],
                            },
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (secrets_dir / "hysteria-config.yaml").write_text(
        json.dumps(
            {
                "obfs": {
                    "type": "plain",
                    "salamander": {"password": "stale password"},
                }
            }
        ),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'Password (PublicKey): unexpected-public'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    result = _run_script(
        ROOT / "deploy/files/generate-node-secrets",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "VPN_SECRETS_DIR": str(secrets_dir),
            "XRAY_IMAGE": "example.invalid/xray@sha256:test",
        },
    )

    assert result.returncode != 0
    assert not (secrets_dir / "node-secrets.json").exists()


def test_node_secret_generator_refuses_a_concurrent_invocation(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / ".node-secrets.lock").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'PrivateKey: unexpected-private' "
        "'Password (PublicKey): unexpected-public'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    openssl = bin_dir / "openssl"
    openssl.write_text(
        "#!/bin/sh\nprintf '%s\\n' '0011223344556677'\n",
        encoding="utf-8",
    )
    openssl.chmod(0o755)

    result = _run_script(
        ROOT / "deploy/files/generate-node-secrets",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "VPN_SECRETS_DIR": str(secrets_dir),
            "XRAY_IMAGE": "example.invalid/xray@sha256:test",
        },
    )

    assert result.returncode != 0
    assert not (secrets_dir / "node-secrets.json").exists()


def test_node_secret_generator_cleans_up_when_interrupted(tmp_path: Path) -> None:
    secrets_dir = tmp_path / "secrets"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    started = tmp_path / "started"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "touch \"$STARTED_FILE\"\n"
        "sleep 30\n"
        "printf '%s\\n' 'PrivateKey: unexpected-private' "
        "'Password (PublicKey): unexpected-public'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    process = subprocess.Popen(
        [str(ROOT / "deploy/files/generate-node-secrets")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "VPN_SECRETS_DIR": str(secrets_dir),
            "XRAY_IMAGE": "example.invalid/xray@sha256:test",
            "STARTED_FILE": str(started),
        },
        start_new_session=True,
    )
    deadline = time.monotonic() + 3
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert started.exists()

    os.killpg(process.pid, signal.SIGTERM)
    process.communicate(timeout=3)

    assert process.returncode != 0
    assert not (secrets_dir / "node-secrets.json").exists()
    assert not (secrets_dir / ".node-secrets.lock").exists()


def test_node_secret_generator_rejects_invalid_legacy_short_id(
    tmp_path: Path,
) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    inbound = {
        "tag": "vless-reality",
        "protocol": "vless",
        "streamSettings": {
            "security": "reality",
            "realitySettings": {
                "privateKey": "legacy-private",
                "shortIds": ["abc"],
            },
        },
    }
    (secrets_dir / "xray-config.json").write_text(
        json.dumps({"inbounds": [inbound]}), encoding="utf-8"
    )
    (secrets_dir / "hysteria-config.yaml").write_text(
        json.dumps(
            {"obfs": {"type": "salamander", "salamander": {"password": "ok"}}}
        ),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'Password (PublicKey): unexpected-public'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    result = _run_script(
        ROOT / "deploy/files/generate-node-secrets",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "VPN_SECRETS_DIR": str(secrets_dir),
            "XRAY_IMAGE": "example.invalid/xray@sha256:test",
        },
    )

    assert result.returncode != 0
    assert not (secrets_dir / "node-secrets.json").exists()


def test_node_secret_generator_rejects_ambiguous_reality_inbounds(
    tmp_path: Path,
) -> None:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    inbound = {
        "tag": "vless-reality",
        "protocol": "vless",
        "streamSettings": {
            "security": "reality",
            "realitySettings": {
                "privateKey": "legacy-private",
                "shortIds": ["aabb"],
            },
        },
    }
    (secrets_dir / "xray-config.json").write_text(
        json.dumps({"inbounds": [inbound, inbound]}), encoding="utf-8"
    )
    (secrets_dir / "hysteria-config.yaml").write_text(
        json.dumps(
            {"obfs": {"type": "salamander", "salamander": {"password": "ok"}}}
        ),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'Password (PublicKey): unexpected-public'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    result = _run_script(
        ROOT / "deploy/files/generate-node-secrets",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "VPN_SECRETS_DIR": str(secrets_dir),
            "XRAY_IMAGE": "example.invalid/xray@sha256:test",
        },
    )

    assert result.returncode != 0
    assert not (secrets_dir / "node-secrets.json").exists()


def test_certificate_deploy_hook_installs_renewed_files_and_recreates_hysteria(
    tmp_path: Path,
) -> None:
    lineage = tmp_path / "lineage"
    lineage.mkdir()
    (lineage / "fullchain.pem").write_text("renewed certificate", encoding="utf-8")
    (lineage / "privkey.pem").write_text("renewed private key", encoding="utf-8")
    deploy_root = tmp_path / "vpn-node"
    (deploy_root / "secrets").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker.log"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "if [ \"$*\" = 'compose ps --status running --services hysteria' ]; then\n"
        "  printf '%s\\n' hysteria\n"
        "else\n"
        "  printf 'cwd=%s args=%s\\n' \"$PWD\" \"$*\" > \"$DOCKER_LOG\"\n"
        "fi\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    result = _run_script(
        ROOT / "deploy/files/renew-hysteria-certificate",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "RENEWED_LINEAGE": str(lineage),
            "VPN_CERTIFICATE_LINEAGE": str(lineage),
            "VPN_DEPLOY_ROOT": str(deploy_root),
            "VPN_HYSTERIA_RESTART_DELAY": "0",
            "DOCKER_LOG": str(docker_log),
        },
    )

    assert result.returncode == 0, result.stderr
    certificate = deploy_root / "secrets/hysteria-tls.crt"
    private_key = deploy_root / "secrets/hysteria-tls.key"
    assert certificate.read_text(encoding="utf-8") == "renewed certificate"
    assert private_key.read_text(encoding="utf-8") == "renewed private key"
    assert stat.S_IMODE(certificate.stat().st_mode) == 0o400
    assert stat.S_IMODE(private_key.stat().st_mode) == 0o400
    assert docker_log.read_text(encoding="utf-8") == (
        f"cwd={deploy_root} "
        "args=compose up -d --no-deps --force-recreate hysteria\n"
    )


def test_certificate_deploy_hook_ignores_an_unrelated_lineage(tmp_path: Path) -> None:
    expected_lineage = tmp_path / "expected-lineage"
    expected_lineage.mkdir()
    unrelated_lineage = tmp_path / "unrelated-lineage"
    unrelated_lineage.mkdir()
    (unrelated_lineage / "fullchain.pem").write_text("wrong cert", encoding="utf-8")
    (unrelated_lineage / "privkey.pem").write_text("wrong key", encoding="utf-8")
    deploy_root = tmp_path / "vpn-node"
    secrets_dir = deploy_root / "secrets"
    secrets_dir.mkdir(parents=True)
    certificate = secrets_dir / "hysteria-tls.crt"
    private_key = secrets_dir / "hysteria-tls.key"
    certificate.write_text("right cert", encoding="utf-8")
    private_key.write_text("right key", encoding="utf-8")

    result = _run_script(
        ROOT / "deploy/files/renew-hysteria-certificate",
        env={
            "RENEWED_LINEAGE": str(unrelated_lineage),
            "VPN_CERTIFICATE_LINEAGE": str(expected_lineage),
            "VPN_DEPLOY_ROOT": str(deploy_root),
        },
    )

    assert result.returncode == 0, result.stderr
    assert certificate.read_text(encoding="utf-8") == "right cert"
    assert private_key.read_text(encoding="utf-8") == "right key"


def test_certificate_deploy_hook_fails_when_hysteria_does_not_stay_running(
    tmp_path: Path,
) -> None:
    lineage = tmp_path / "lineage"
    lineage.mkdir()
    (lineage / "fullchain.pem").write_text("renewed certificate", encoding="utf-8")
    (lineage / "privkey.pem").write_text("renewed private key", encoding="utf-8")
    deploy_root = tmp_path / "vpn-node"
    (deploy_root / "secrets").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    docker.chmod(0o755)

    result = _run_script(
        ROOT / "deploy/files/renew-hysteria-certificate",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "RENEWED_LINEAGE": str(lineage),
            "VPN_CERTIFICATE_LINEAGE": str(lineage),
            "VPN_DEPLOY_ROOT": str(deploy_root),
            "VPN_HYSTERIA_RESTART_DELAY": "0",
        },
    )

    assert result.returncode != 0


def test_deploy_configures_ip_hostname_certificate_renewal_and_public_output() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")

    assert "replace('.', '-') ~ '.sslip.io'" in playbook
    assert "certbot certonly" in playbook
    assert "--standalone" in playbook
    assert "--keep-until-expiring" in playbook
    assert "/etc/letsencrypt/renewal-hooks/deploy/vpn-node-hysteria" in playbook
    assert "/etc/default/vpn-node-certificate" in playbook
    assert "certbot.timer" in playbook
    assert "docker compose ps --status running --services hysteria" in playbook
    assert "reality_public_key" in playbook
    assert "management_url" in playbook
    assert "vpn_node_secrets.reality_short_id | length == 16" not in playbook
    assert "vpn_node_secrets.hysteria_obfs | length == 64" not in playbook

    certificate_tasks = playbook[
        playbook.index("Request the Hysteria certificate with renewal email") :
        playbook.index("Install the current Hysteria certificate")
    ]
    assert "creates:" not in certificate_tasks


def test_deploy_reads_only_the_shared_token_from_the_controller() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")

    assert "playbook_dir ~ '/secrets/vpn-agent-token'" in playbook
    assert "'ansible.builtin.file'," in playbook
    assert "vpn_agent_token_file_effective," in playbook
    assert "vpn_reality_private_key" not in playbook
    assert "vpn_hysteria_tls_key" not in playbook
    assert playbook.count("no_log: true") >= 3
    assert 'mode: "0400"' in playbook


def test_templates_are_rendered_from_the_github_checkout() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")

    xray_source = 'src: "{{ vpn_deploy_root }}/xray/config.json"'
    hysteria_source = 'src: "{{ vpn_deploy_root }}/hysteria/config.yaml"'
    assert xray_source in playbook
    assert hysteria_source in playbook

    checkout = playbook.index("Clone or update repository from GitHub")
    xray_slurp = playbook.index(xray_source)
    hysteria_slurp = playbook.index(hysteria_source)
    render = playbook.index("Render transport configuration")
    assert checkout < xray_slurp < render
    assert checkout < hysteria_slurp < render


def test_xray_and_agent_are_recreated_when_reality_config_changes() -> None:
    playbook = (ROOT / "deploy/playbook.yml").read_text(encoding="utf-8")

    render = playbook.index("Render Xray REALITY configuration")
    reload_runtime = playbook.index(
        "Reload Xray and agent after REALITY configuration changes"
    )
    apply_runtime = playbook.index("Apply runtime configuration")
    assert render < reload_runtime < apply_runtime

    render_tasks = playbook[render:reload_runtime]
    assert "register: vpn_xray_runtime_config" in render_tasks

    reload_tasks = playbook[reload_runtime:apply_runtime]
    assert "docker compose up -d --force-recreate xray agent" in reload_tasks
    assert "when: vpn_xray_runtime_config.changed" in reload_tasks


def test_example_inventory_and_vars_have_no_real_server_or_credentials() -> None:
    inventory = (ROOT / "deploy/inventory.example.ini").read_text(encoding="utf-8")
    variables = (ROOT / "deploy/group_vars/vpn.example.yml").read_text(
        encoding="utf-8"
    )

    assert re.search(r"(?:\d{1,3}\.){3}\d{1,3}", inventory) is None
    assert "vpn-node ansible_host=vpn-node.example.invalid" in inventory
    host_line = next(line for line in inventory.splitlines() if line.startswith("vpn-node "))
    assert "ansible_user" not in host_line
    assert "ansible_ssh_private_key_file" not in host_line
    assert "[vpn:vars]" in inventory
    assert "ansible_user=root" in inventory
    assert "ansible_ssh_private_key_file=~/.ssh/id_ed25519_deploy" in inventory
    assert "vpn_agent_token" not in variables
    assert "private_key" not in variables
    assert "tls_key" not in variables
    assert "vpn_certbot_email" in variables


def test_hysteria_only_deploy_removes_existing_xray_before_starting_services() -> None:
    playbook = (ROOT / 'deploy/playbook.yml').read_text()
    assert 'vpn_vless_enabled | default(true) | bool' in playbook
    remove = playbook.index('Remove the existing Xray container on Hysteria-only nodes')
    apply = playbook.index('Apply runtime configuration')
    assert remove < apply
    removal = playbook[remove:playbook.index('Create private runtime directory')]
    assert 'docker compose --profile disabled rm --stop --force xray' in removal
    assert 'when: not (vpn_vless_enabled_effective | bool)' in removal
    assert 'when: vpn_xray_runtime_config.changed and (vpn_vless_enabled_effective | bool)' in playbook
    assert 'Restore dual-protocol Compose configuration' in playbook
