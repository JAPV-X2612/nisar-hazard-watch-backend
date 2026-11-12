import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from nisar_hazard_watch.adapters.credentials.configured_probe import ConfiguredProbe
from nisar_hazard_watch.adapters.db.database_probe import DatabaseProbe
from nisar_hazard_watch.adapters.nasa.cmr_probe import CmrProbe
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.health import DependencyName
from nisar_hazard_watch.services.health_service import HealthService


def build_health_service(
    settings: Settings, engine: AsyncEngine, http_client: httpx.AsyncClient
) -> HealthService:
    modal_configured = (
        settings.modal_token_id is not None and settings.modal_token_secret is not None
    )
    probes = [
        DatabaseProbe(engine=engine, timeout_seconds=settings.database_health_timeout_seconds),
        CmrProbe(client=http_client, health_url=settings.cmr_health_url),
        ConfiguredProbe(name=DependencyName.MODAL, configured=modal_configured),
        ConfiguredProbe(
            name=DependencyName.EARTHDATA_TOKEN,
            configured=settings.earthdata_token is not None,
        ),
    ]
    return HealthService(
        probes=probes,
        service_name=settings.service_name,
        version=settings.version,
        environment=settings.environment,
        probe_timeout_seconds=settings.health_probe_timeout_seconds,
    )
