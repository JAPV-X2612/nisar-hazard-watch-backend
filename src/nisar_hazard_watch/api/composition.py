import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from nisar_hazard_watch.adapters.asf.asf_catalog import AsfCatalog
from nisar_hazard_watch.adapters.cases.static_precomputed_cases import StaticPrecomputedCases
from nisar_hazard_watch.adapters.credentials.configured_probe import ConfiguredProbe
from nisar_hazard_watch.adapters.db.database_probe import DatabaseProbe
from nisar_hazard_watch.adapters.db.job_repository import SqlJobRepository
from nisar_hazard_watch.adapters.firms.firms_client import FirmsClient
from nisar_hazard_watch.adapters.gateway.gateway_case_catalog import GatewayCaseCatalog
from nisar_hazard_watch.adapters.gateway.gateway_insar_catalog import GatewayInsarCatalog
from nisar_hazard_watch.adapters.geocoding.nominatim_geocoder import NominatimGeocoder
from nisar_hazard_watch.adapters.nasa.cmr_probe import CmrProbe
from nisar_hazard_watch.adapters.runners.gateway_runner import GatewayRunner
from nisar_hazard_watch.adapters.runners.in_process_runner import InProcessRunner
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.cases import CASES_CACHE_TTL_SECONDS, CASES_RETRY_AFTER_SECONDS
from nisar_hazard_watch.constants.explorations import RunnerKind
from nisar_hazard_watch.constants.health import DependencyName
from nisar_hazard_watch.hazards.earthquake.insar_pairs_service import InsarPairsService
from nisar_hazard_watch.hazards.wildfire.fire_context_provider import FirmsFireContextProvider
from nisar_hazard_watch.ports.analysis_runner import AnalysisRunner
from nisar_hazard_watch.services.case_service import CaseService
from nisar_hazard_watch.services.eta_estimator import EtaEstimator
from nisar_hazard_watch.services.exploration_service import ExplorationService
from nisar_hazard_watch.services.health_service import HealthService
from nisar_hazard_watch.services.place_search_service import PlaceSearchService
from nisar_hazard_watch.services.scene_planner import ScenePlanner


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


def build_insar_pairs_service(
    settings: Settings, gateway_client: httpx.AsyncClient
) -> InsarPairsService:
    return InsarPairsService(
        catalog=GatewayInsarCatalog(client=gateway_client, base_url=settings.ml_gateway_url)
    )


def build_case_service(settings: Settings, gateway_client: httpx.AsyncClient) -> CaseService:
    return CaseService(
        catalog=GatewayCaseCatalog(client=gateway_client, base_url=settings.ml_gateway_url),
        ttl_seconds=CASES_CACHE_TTL_SECONDS,
        retry_after_seconds=CASES_RETRY_AFTER_SECONDS,
    )


def build_exploration_service(
    settings: Settings,
    engine: AsyncEngine,
    asf_client: httpx.AsyncClient,
    gateway_client: httpx.AsyncClient,
    firms_client: httpx.AsyncClient,
    runner: AnalysisRunner | None = None,
) -> ExplorationService:
    repository = SqlJobRepository(
        session_factory=async_sessionmaker(engine, expire_on_commit=False)
    )
    if runner is None:
        runner = (
            InProcessRunner()
            if settings.runner is RunnerKind.IN_PROCESS
            else GatewayRunner(client=gateway_client, base_url=settings.ml_gateway_url)
        )
    fire_source = (
        FirmsClient(
            client=firms_client, base_url=settings.firms_url, map_key=settings.firms_map_key
        )
        if settings.firms_map_key is not None
        else None
    )
    return ExplorationService(
        planner=ScenePlanner(catalog=AsfCatalog(client=asf_client)),
        runner=runner,
        repository=repository,
        eta=EtaEstimator(repository=repository, prior_seconds=settings.eta_prior_seconds),
        cases=StaticPrecomputedCases.from_file(path=settings.precomputed_cases_path),
        max_active=settings.max_active_explorations,
        deadline_seconds=settings.exploration_deadline_seconds,
        cache_ttl_seconds=settings.exploration_cache_ttl_seconds,
        fire_context=FirmsFireContextProvider(
            source=fire_source, timeout_seconds=settings.fire_context_timeout_seconds
        ),
    )


def build_place_search_service(
    settings: Settings, geocoder_client: httpx.AsyncClient
) -> PlaceSearchService:
    return PlaceSearchService(
        geocoder=NominatimGeocoder(client=geocoder_client, base_url=settings.geocoder_url)
    )
