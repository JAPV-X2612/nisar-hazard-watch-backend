from pathlib import Path

import pytest

from nisar_hazard_watch.config.settings import Settings, get_settings
from nisar_hazard_watch.constants.environments import Environment

LOCAL_ORIGIN = "http://localhost:5173"
VERCEL_ORIGIN = "https://nisar-hazard-watch-nine.vercel.app"
RAILWAY_DATABASE_URL = "postgresql://user:secret@postgres.railway.internal:5432/railway"
EXPECTED_ASYNC_URL = "postgresql+asyncpg://user:secret@postgres.railway.internal:5432/railway"
SECRET_VALUE = "super-secret-token"
SETTING_ENV_NAMES = (
    "ENVIRONMENT",
    "LOG_LEVEL",
    "DATABASE_URL",
    "CORS_ALLOWED_ORIGINS",
    "EARTHDATA_TOKEN",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env file is picked up
    for name in SETTING_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_defaults_describe_a_local_environment() -> None:
    # Arrange / Act
    settings = Settings()

    # Assert
    assert settings.environment is Environment.LOCAL
    assert settings.cors_allowed_origins == [LOCAL_ORIGIN]
    assert settings.earthdata_token is None
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_database_url_from_the_platform_gets_the_async_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("DATABASE_URL", RAILWAY_DATABASE_URL)

    # Act
    settings = Settings()

    # Assert
    assert settings.database_url == EXPECTED_ASYNC_URL


def test_origins_can_be_a_comma_separated_list(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", f"{LOCAL_ORIGIN}, {VERCEL_ORIGIN} ,")

    # Act
    settings = Settings()

    # Assert
    assert settings.cors_allowed_origins == [LOCAL_ORIGIN, VERCEL_ORIGIN]


def test_origins_can_be_a_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", f'["{VERCEL_ORIGIN}"]')

    # Act
    settings = Settings()

    # Assert
    assert settings.cors_allowed_origins == [VERCEL_ORIGIN]


def test_secrets_never_show_up_in_the_representation(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("EARTHDATA_TOKEN", SECRET_VALUE)

    # Act
    settings = Settings()

    # Assert
    assert settings.earthdata_token is not None
    assert settings.earthdata_token.get_secret_value() == SECRET_VALUE
    assert SECRET_VALUE not in repr(settings)


def test_get_settings_is_cached() -> None:
    # Arrange
    get_settings.cache_clear()

    # Act
    first = get_settings()
    second = get_settings()

    # Assert
    assert first is second
