import httpx
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import create_async_engine

from nisar_hazard_watch.api.composition import build_health_service
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.constants.health import DependencyName, DependencyState

UNREACHABLE_CMR_URL = "http://127.0.0.1:9/health"
CLIENT_TIMEOUT_SECONDS = 0.5
SQLITE_MEMORY_URL = "sqlite+aiosqlite://"


async def _dependency_states(settings: Settings) -> dict[DependencyName, DependencyState]:
    engine = create_async_engine(settings.database_url)
    async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT_SECONDS) as client:
        service = build_health_service(settings=settings, engine=engine, http_client=client)
        report = await service.check()
    await engine.dispose()
    return {name: dependency.state for name, dependency in report.dependencies.items()}


async def test_credentials_are_reported_as_configured_only_when_present() -> None:
    # Arrange
    settings = Settings(
        environment=Environment.TEST,
        database_url=SQLITE_MEMORY_URL,
        cmr_health_url=UNREACHABLE_CMR_URL,
        earthdata_token=SecretStr("a-token"),
        modal_token_id=SecretStr("id"),
        modal_token_secret=SecretStr("secret"),
    )

    # Act
    states = await _dependency_states(settings)

    # Assert
    assert states[DependencyName.DATABASE] is DependencyState.OK
    assert states[DependencyName.MODAL] is DependencyState.CONFIGURED
    assert states[DependencyName.EARTHDATA_TOKEN] is DependencyState.CONFIGURED


async def test_missing_credentials_are_reported_as_not_configured() -> None:
    # Arrange
    settings = Settings(
        environment=Environment.TEST,
        database_url=SQLITE_MEMORY_URL,
        cmr_health_url=UNREACHABLE_CMR_URL,
    )

    # Act
    states = await _dependency_states(settings)

    # Assert
    assert states[DependencyName.MODAL] is DependencyState.NOT_CONFIGURED
    assert states[DependencyName.EARTHDATA_TOKEN] is DependencyState.NOT_CONFIGURED
