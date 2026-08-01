from __future__ import annotations

from dataclasses import dataclass
from os import environ


@dataclass(frozen=True, kw_only=True, slots=True)
class Settings:
    agent_token: str
    backend_url: str = "http://backend"
    xray_api_address: str = "127.0.0.1:10085"
    xray_vless_inbound_tag: str = "vless-reality"

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            agent_token=environ["VPN_AGENT_TOKEN"],
            backend_url=environ["VPN_BACKEND_URL"],
            xray_api_address=environ.get("XRAY_API_ADDRESS", "127.0.0.1:10085"),
            xray_vless_inbound_tag=environ["XRAY_VLESS_INBOUND_TAG"],
        )
