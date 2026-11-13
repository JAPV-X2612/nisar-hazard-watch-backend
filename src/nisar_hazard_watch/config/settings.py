import json
import re
from functools import lru_cache
from typing import Annotated, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from nisar_hazard_watch import __version__
from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.constants.explorations import RunnerKind
from nisar_hazard_watch.constants.log_levels import LogLevel
from nisar_hazard_watch.constants.places import DEFAULT_GEOCODER_URL
from nisar_hazard_watch.utils.database_url import to_async_database_url

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/nisar_hazard_watch"
DEFAULT_CORS_ORIGINS = ["http://localhost:5173"]
DEFAULT_CMR_HEALTH_URL = "https://cmr.earthdata.nasa.gov/search/health"
DEFAULT_ML_GATEWAY_URL = "https://ch0comilo--nisar-hazard-watch-ml.us-east.modal.run"
# Railway's edge appends two entries (measured 2026-11-12): the client is second from the right.
DEFAULT_TRUSTED_PROXY_HOPS = 2
ORIGIN_PATTERN = re.compile(r"^https?://[^/\s]+$")
SECRET_FIELDS = ("earthdata_token", "modal_token_id", "modal_token_secret")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "nisar-hazard-watch-backend"
    version: str = __version__
    environment: Environment = Environment.LOCAL
    log_level: LogLevel = LogLevel.INFO
    database_url: str = Field(default=DEFAULT_DATABASE_URL, repr=False, exclude=True)
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_CORS_ORIGINS)
    )
    cmr_health_url: str = DEFAULT_CMR_HEALTH_URL
    cmr_health_timeout_seconds: float = Field(default=5.0, gt=0)
    database_health_timeout_seconds: float = Field(default=3.0, gt=0)
    health_probe_timeout_seconds: float = Field(default=10.0, gt=0)
    ml_gateway_url: str = DEFAULT_ML_GATEWAY_URL
    runner: RunnerKind = RunnerKind.GATEWAY
    asf_timeout_seconds: float = Field(default=30.0, gt=0)
    gateway_timeout_seconds: float = Field(default=20.0, gt=0)
    geocoder_url: str = DEFAULT_GEOCODER_URL
    geocoder_timeout_seconds: float = Field(default=8.0, gt=0)
    max_active_explorations: int = Field(default=5, ge=1)
    exploration_deadline_seconds: float = Field(default=55.0, gt=0)
    exploration_cache_ttl_seconds: float = Field(default=86400.0, gt=0)
    rate_limit_per_minute: int = Field(default=20, ge=1)
    trusted_proxy_hops: int = Field(default=DEFAULT_TRUSTED_PROXY_HOPS, ge=0)
    eta_prior_seconds: float = Field(default=60.0, gt=0)
    precomputed_cases_path: str | None = None
    earthdata_token: SecretStr | None = None
    modal_token_id: SecretStr | None = None
    modal_token_secret: SecretStr | None = None

    @field_validator("log_level", mode="before")
    @classmethod
    def _accept_any_case_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator(*SECRET_FIELDS, mode="before")
    @classmethod
    def _treat_blank_secrets_as_missing(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def _use_the_async_driver(cls, value: str) -> str:
        return to_async_database_url(url=value)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            return json.loads(text)
        return [origin.strip() for origin in text.split(",") if origin.strip()]

    @field_validator("cors_allowed_origins")
    @classmethod
    def _require_well_formed_origins(cls, origins: list[str]) -> list[str]:
        if not origins:
            raise ValueError("at least one origin is required")
        malformed = [origin for origin in origins if not ORIGIN_PATTERN.fullmatch(origin)]
        if malformed:
            raise ValueError(
                f"origins must look like https://host[:port] without a path: {malformed!r}"
            )
        return origins

    @model_validator(mode="after")
    def _require_database_url_in_production(self) -> Self:
        explicit_database_url = "database_url" in self.model_fields_set
        if self.environment is Environment.PRODUCTION and not explicit_database_url:
            raise ValueError("DATABASE_URL must be set when ENVIRONMENT=production")
        return self

    @model_validator(mode="after")
    def _forbid_the_synthetic_runner_in_production(self) -> Self:
        if self.environment is Environment.PRODUCTION and self.runner is RunnerKind.IN_PROCESS:
            raise ValueError(
                "RUNNER=inProcess returns synthetic results, not allowed in production"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
