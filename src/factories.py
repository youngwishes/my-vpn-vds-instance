from __future__ import annotations

from .domain.store import InMemoryProfileStore


def create_profile_store() -> InMemoryProfileStore:
    return InMemoryProfileStore()
