from collections.abc import Callable

import httpx
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import create_async_engine

from nisar_hazard_watch.api.composition import build_health_service
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.health import DependencyName, DependencyState


def _unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("no route", request=request)


async def _dependency_states(settings: Settings) -> dict[DependencyName, DependencyState]:
    engine = create_async_engine(settings.database_url)
    async with httpx.AsyncClient(transport=httpx.MockTransport(_unreachable)) as client:
        service = build_health_service(settings=settings, engine=engine, http_client=client)
        report = await service.check()
    await engine.dispose()
    return {name: dependency.state for name, dependency in report.dependencies.items()}


async def test_credentials_are_reported_as_configured_only_when_present(
    make_settings: Callable[..., Settings],
) -> None:
    # Arrange
    settings = make_settings(
        earthdata_token=SecretStr("a-token"),
        modal_token_id=SecretStr("id"),
        modal_token_secret=SecretStr("sec"),
    )

    # Act
    states = await _dependency_states(settings=settings)

    # Assert
    assert states[DependencyName.DATABASE] is DependencyState.OK
    assert states[DependencyName.MODAL] is DependencyState.CONFIGURED
    assert states[DependencyName.EARTHDATA_TOKEN] is DependencyState.CONFIGURED


async def test_missing_credentials_are_reported_as_not_configured(
    make_settings: Callable[..., Settings],
) -> None:
    # Arrange
    settings = make_settings()

    # Act
    states = await _dependency_states(settings=settings)

    # Assert
    assert states[DependencyName.MODAL] is DependencyState.NOT_CONFIGURED
    assert states[DependencyName.EARTHDATA_TOKEN] is DependencyState.NOT_CONFIGURED


async def test_modal_needs_both_halves_of_its_token_to_count_as_configured(
    make_settings: Callable[..., Settings],
) -> None:
    # Arrange
    settings = make_settings(modal_token_id=SecretStr("id"))

    # Act
    states = await _dependency_states(settings=settings)

    # Assert
    assert states[DependencyName.MODAL] is DependencyState.NOT_CONFIGURED
