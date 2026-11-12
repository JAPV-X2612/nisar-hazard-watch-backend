import json
import re
from functools import lru_cache
from typing import Annotated, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from nisar_hazard_watch import __version__
from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.constants.log_levels import LogLevel
from nisar_hazard_watch.utils.database_url import to_async_database_url

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/nisar_hazard_watch"
DEFAULT_CORS_ORIGINS = ["http://localhost:5173"]
DEFAULT_CMR_HEALTH_URL = "https://cmr.earthdata.nasa.gov/search/health"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
