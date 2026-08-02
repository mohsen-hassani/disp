from base64 import urlsafe_b64decode
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DISP_", env_file=".env", extra="forbid")

    database_url: str
    database_url_sync: str = ""
    jwt_secret: SecretStr
    settings_key: SecretStr
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_seconds: int = Field(default=2_592_000, ge=3600, le=7_776_000)
    invite_ttl_seconds: int = Field(default=604_800, ge=3600, le=2_592_000)
    pat_default_ttl_days: int | None = Field(default=None, ge=1)
    modules: str = ""
    base_url: str
    cors_origins: str = ""
    cookie_secure: bool = True
    cookie_domain: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    daily_planner_cron: str = "0 6 * * *"
    timezone: str = "Europe/Amsterdam"
    rate_limit_enabled: bool = True
    env: Literal["production", "development", "test"] = "production"

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DISP_DATABASE_URL must start with postgresql+asyncpg://")
        return v

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str) -> str:
        if v.endswith("/"):
            raise ValueError("DISP_BASE_URL must not have a trailing slash")
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("DISP_JWT_SECRET must be at least 32 characters")
        return v

    @field_validator("settings_key")
    @classmethod
    def _validate_settings_key(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        try:
            decoded = urlsafe_b64decode(raw.encode("ascii"))
        except Exception as exc:
            raise ValueError(
                "DISP_SETTINGS_KEY must be a valid urlsafe-base64 Fernet key"
            ) from exc
        if len(decoded) != 32:
            raise ValueError("DISP_SETTINGS_KEY must decode to exactly 32 bytes")
        return v

    @model_validator(mode="before")
    @classmethod
    def _derive_database_url_sync(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("database_url_sync"):
            database_url = data.get("database_url") or ""
            data["database_url_sync"] = database_url.replace("+asyncpg", "+psycopg", 1)
        return data

    @model_validator(mode="after")
    def _validate_production_cookie_secure(self) -> "Settings":
        if self.env == "production" and not self.cookie_secure:
            raise ValueError("DISP_COOKIE_SECURE must be true when DISP_ENV=production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def module_allow_list(self) -> list[str]:
        return [name.strip() for name in self.modules.split(",") if name.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
