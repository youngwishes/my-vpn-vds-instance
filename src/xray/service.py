from __future__ import annotations

from typing import Protocol
from uuid import UUID


class XrayClient(Protocol):
    def upsert_user(self, *, access_id: int, uuid: UUID) -> None: ...

    def delete_user(self, *, access_id: int) -> None: ...

    def health(self) -> None: ...
