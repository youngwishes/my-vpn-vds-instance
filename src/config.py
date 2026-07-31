from __future__ import annotations

from dataclasses import dataclass
from os import environ


@dataclass(frozen=True, kw_only=True, slots=True)
class Settings:
    agent_token: str

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(agent_token=environ["VPN_AGENT_TOKEN"])
