from __future__ import annotations

import json
import stat
from pathlib import Path
from uuid import UUID

import pytest

from src.xray.client import HandlerServiceXrayClient


def test_handler_service_client_uses_real_cli_argv_and_private_temporary_config() -> None:
    commands: list[tuple[str, ...]] = []
    configs: list[tuple[Path, dict[str, object]]] = []
    removals = 0

    def run(command: tuple[str, ...]) -> str:
        nonlocal removals
        commands.append(command)
        if command[2] == "adu":
            config_path = Path(command[-1])
            assert config_path.exists()
            assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
            configs.append((config_path, json.loads(config_path.read_text())))
            return "Added 1 user(s) in total.\n"
        if command[2] == "rmu":
            removals += 1
            if removals == 1:
                return (
                    "remove user: vpn-42\n"
                    "User vpn-42 not found.\n"
                    "Removed 0 user(s) in total.\n"
                )
            return "remove user: vpn-42\nRemoved 1 user(s) in total.\n"
        return "1\n"

    client = HandlerServiceXrayClient(
        api_address="127.0.0.1:10085",
        inbound_tag="vless-reality",
        command_runner=run,
    )

    client.upsert_user(
        access_id=42,
        uuid=UUID("11111111-1111-1111-1111-111111111111"),
    )
    client.delete_user(access_id=42)
    client.health()

    assert commands == [
        (
            "xray",
            "api",
            "rmu",
            "--server=127.0.0.1:10085",
            "-tag=vless-reality",
            "vpn-42",
        ),
        (
            "xray",
            "api",
            "adu",
            "--server=127.0.0.1:10085",
            str(configs[0][0]),
        ),
        (
            "xray",
            "api",
            "rmu",
            "--server=127.0.0.1:10085",
            "-tag=vless-reality",
            "vpn-42",
        ),
        (
            "xray",
            "api",
            "inboundusercount",
            "--server=127.0.0.1:10085",
            "-tag=vless-reality",
        ),
    ]
    assert configs == [
        (
            configs[0][0],
            {
                "inbounds": [
                    {
                        "tag": "vless-reality",
                        "listen": "127.0.0.1",
                        "port": 1,
                        "protocol": "vless",
                        "settings": {
                            "users": [
                                {
                                    "id": "11111111-1111-1111-1111-111111111111",
                                    "email": "vpn-42",
                                    "flow": "xtls-rprx-vision",
                                }
                            ]
                        },
                    }
                ]
            },
        )
    ]
    assert not configs[0][0].exists()


def test_handler_service_client_rejects_zero_added_users_and_removes_temp_config() -> None:
    config_paths: list[Path] = []

    def run(command: tuple[str, ...]) -> str:
        if command[2] == "adu":
            config_path = Path(command[-1])
            assert config_path.exists()
            config_paths.append(config_path)
            return "Added 0 user(s) in total.\n"
        return (
            "remove user: vpn-42\n"
            "User vpn-42 not found.\n"
            "Removed 0 user(s) in total.\n"
        )

    client = HandlerServiceXrayClient(
        api_address="127.0.0.1:10085",
        inbound_tag="vless-reality",
        command_runner=run,
    )

    with pytest.raises(RuntimeError, match="Xray did not add user"):
        client.upsert_user(
            access_id=42,
            uuid=UUID("11111111-1111-1111-1111-111111111111"),
        )

    assert len(config_paths) == 1
    assert not config_paths[0].exists()


def test_handler_service_client_accepts_exact_prefixed_absent_user_remove_response() -> None:
    client = HandlerServiceXrayClient(
        api_address="127.0.0.1:10085",
        inbound_tag="vless-reality",
        command_runner=lambda _: (
            "remove user: vpn-42\n"
            "User vpn-42 not found.\n"
            "Removed 0 user(s) in total.\n"
        ),
    )

    client.delete_user(access_id=42)


@pytest.mark.parametrize(
    "output",
    [
        "Removed 0 user(s) in total.\n",
        "rpc error: unavailable\nRemoved 0 user(s) in total.\n",
        "User vpn-42 not found.\nRemoved 0 user(s) in total.\n",
        "User vpn-41 not found.\nRemoved 0 user(s) in total.\n",
        "remove user: vpn-41\nUser vpn-42 not found.\nRemoved 0 user(s) in total.\n",
        "remove user: vpn-42\nUser vpn-41 not found.\nRemoved 0 user(s) in total.\n",
    ],
)
def test_handler_service_client_rejects_unconfirmed_zero_user_remove(output: str) -> None:
    client = HandlerServiceXrayClient(
        api_address="127.0.0.1:10085",
        inbound_tag="vless-reality",
        command_runner=lambda _: output,
    )

    with pytest.raises(RuntimeError, match="Xray did not remove user"):
        client.delete_user(access_id=42)


def test_handler_service_client_refuses_upsert_when_initial_remove_is_unconfirmed() -> None:
    commands: list[tuple[str, ...]] = []
    client = HandlerServiceXrayClient(
        api_address="127.0.0.1:10085",
        inbound_tag="vless-reality",
        command_runner=lambda command: commands.append(command) or "Removed 0 user(s) in total.\n",
    )

    with pytest.raises(RuntimeError, match="Xray did not remove user"):
        client.upsert_user(
            access_id=42,
            uuid=UUID("11111111-1111-1111-1111-111111111111"),
        )

    assert [command[2] for command in commands] == ["rmu"]
