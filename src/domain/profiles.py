from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(kw_only=True, slots=True, frozen=True)
class VPNProfile:
    access_id: int
    vless_uuid: UUID
    hysteria_secret: str
