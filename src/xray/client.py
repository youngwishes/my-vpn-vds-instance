from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import final
from uuid import UUID


CommandRunner = Callable[[tuple[str, ...]], str]


def run_xray_command(command: tuple[str, ...]) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError("Xray command failed") from None
    return result.stdout


@final
@dataclass(frozen=True, kw_only=True, slots=True)
class HandlerServiceXrayClient:
    api_address: str
    inbound_tag: str
    command_runner: CommandRunner = run_xray_command

    def upsert_user(self, *, access_id: int, uuid: UUID) -> None:
        self.delete_user(access_id=access_id)
        output = self._add_user(
            access_id=access_id,
            uuid=uuid,
        )
        if "Added 1 user(s) in total." not in output:
            raise RuntimeError("Xray did not add user")

    def delete_user(self, *, access_id: int) -> None:
        email = self._email(access_id=access_id)
        output = self.command_runner(
            (
                "xray",
                "api",
                "rmu",
                f"--server={self.api_address}",
                f"-tag={self.inbound_tag}",
                email,
            )
        )
        if "Removed 1 user(s) in total." in output:
            return
        if output.strip().splitlines() == [
            f"User {email} not found.",
            "Removed 0 user(s) in total.",
        ]:
            return
        raise RuntimeError("Xray did not remove user")

    def health(self) -> None:
        self.command_runner(
            (
                "xray",
                "api",
                "inboundusercount",
                f"--server={self.api_address}",
                f"-tag={self.inbound_tag}",
            )
        )

    def _add_user(self, *, access_id: int, uuid: UUID) -> str:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        ) as config_file:
            os.fchmod(config_file.fileno(), 0o600)
            json.dump(
                {
                    "inbounds": [
                        {
                            "tag": self.inbound_tag,
                            "listen": "127.0.0.1",
                            "port": 1,
                            "protocol": "vless",
                            "settings": {
                                "users": [
                                    {
                                        "id": str(uuid),
                                        "email": self._email(access_id=access_id),
                                        "flow": "xtls-rprx-vision",
                                    }
                                ]
                            },
                        }
                    ]
                },
                config_file,
            )
            config_path = config_file.name

        try:
            return self.command_runner(
                (
                    "xray",
                    "api",
                    "adu",
                    f"--server={self.api_address}",
                    config_path,
                )
            )
        finally:
            os.unlink(config_path)

    @staticmethod
    def _email(*, access_id: int) -> str:
        return f"vpn-{access_id}"
