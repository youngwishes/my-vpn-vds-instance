from __future__ import annotations

from .health import router as health_router
from .management import router as management_router

__all__ = ["health_router", "management_router"]
