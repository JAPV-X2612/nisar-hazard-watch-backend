from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.environments import Environment
from tests.constants import CMR_HEALTH_URL, SQLITE_MEMORY_URL

SETTING_ENV_NAMES = (
    "ENVIRONMENT",
    "LOG_LEVEL",
    "DATABASE_URL",
    "CORS_ALLOWED_ORIGINS",
    "CMR_HEALTH_URL",
    "CMR_HEALTH_TIMEOUT_SECONDS",
    "DATABASE_HEALTH_TIMEOUT_SECONDS",
    "HEALTH_PROBE_TIMEOUT_SECONDS",
    "EARTHDATA_TOKEN",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "RUNNER",
    "ML_GATEWAY_URL",
    "MAX_ACTIVE_EXPLORATIONS",
    "EXPLORATION_DEADLINE_SECONDS",
    "EXPLORATION_CACHE_TTL_SECONDS",
    "RATE_LIMIT_PER_MINUTE",
    "ETA_PRIOR_SECONDS",
    "ASF_TIMEOUT_SECONDS",
    "GATEWAY_TIMEOUT_SECONDS",
    "FIRMS_MAP_KEY",
    "FIRMS_URL",
    "FIRMS_TIMEOUT_SECONDS",
    "FIRE_CONTEXT_TIMEOUT_SECONDS",
    "GEOCODER_URL",
    "GEOCODER_TIMEOUT_SECONDS",
    "PRECOMPUTED_CASES_PATH",
)


@pytest.fixture(autouse=True)
def isolated_settings_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env file is picked up
    for name in SETTING_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    def build(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "environment": Environment.TEST,
            "database_url": SQLITE_MEMORY_URL,
            "cmr_health_url": CMR_HEALTH_URL,
            **overrides,
        }
        return Settings(**values)

    return build
