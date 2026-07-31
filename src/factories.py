from __future__ import annotations

from .backend.client import DjangoBackendClient
from .config import Settings
from .domain.store import InMemoryProfileStore
from .services.bootstrap_service import BootstrapService, BootstrapState
from .services.profile_service import ProfileService
from .xray.client import HandlerServiceXrayClient
from .xray.service import XrayClient


def create_profile_store() -> InMemoryProfileStore:
    return InMemoryProfileStore()


def create_xray_client(*, settings: Settings) -> HandlerServiceXrayClient:
    return HandlerServiceXrayClient(
        api_address=settings.xray_api_address,
        inbound_tag=settings.xray_vless_inbound_tag,
    )


def create_profile_service(
    *,
    profile_store: InMemoryProfileStore,
    xray_client: XrayClient,
) -> ProfileService:
    return ProfileService(profile_store=profile_store, xray_client=xray_client)


def create_bootstrap_service(
    *,
    settings: Settings,
    profile_service: ProfileService,
) -> BootstrapService:
    return BootstrapService(
        backend_client=DjangoBackendClient(
            backend_url=settings.backend_url,
            agent_token=settings.agent_token,
        ),
        profile_service=profile_service,
        state=BootstrapState(),
    )
