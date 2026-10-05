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

    # M18 v2: core file service (src/disp/core/files/) — S3-compatible
    # object storage only (Cloudflare R2 in production, MinIO elsewhere).
    files_backend: Literal["s3"] = "s3"
    files_s3_bucket: str = ""
    files_s3_endpoint_url: str | None = None
    files_s3_public_endpoint_url: str | None = None
    files_s3_region: str = "auto"
    files_s3_access_key_id: SecretStr = SecretStr("")
    files_s3_secret_access_key: SecretStr = SecretStr("")
    files_s3_prefix: str = ""
    files_s3_force_path_style: bool = True
    files_max_bytes: int = Field(default=104_857_600, gt=0)
    files_default_link_ttl_seconds: int = Field(default=3600, ge=60, le=604_800)
    files_orphan_grace_seconds: int = Field(default=3600, gt=0)
    files_sweep_cron: str = "17 * * * *"

    # M19: core LLM service (src/disp/core/llm/).
    llm_enabled: bool = False
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "claude-opus-5"
    llm_fast_model: str = "claude-haiku-4-5"
    llm_max_output_tokens: int = Field(default=16000, gt=0)
    llm_timeout_seconds: int = Field(default=600, ge=10, le=1800)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    embedding_enabled: bool = False
    embedding_provider: Literal["voyage", "local"] = "voyage"
    embedding_api_key: SecretStr = SecretStr("")
    embedding_model: str = "voyage-3"
    embedding_dimensions: int = Field(default=1024, gt=0)

    # M22: core translation service (src/disp/core/translation/).
    translation_enabled: bool = False
    translation_backend: Literal["deepl", "fake"] = "deepl"
    translation_api_key: SecretStr = SecretStr("")
    translation_base_url: str = ""
    translation_default_target_lang: str = ""
    translation_timeout_seconds: int = Field(default=30, ge=1, le=300)
    translation_max_retries: int = Field(default=2, ge=0)
    translation_max_chars: int = Field(default=120_000, gt=0)

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
            raise ValueError("DISP_SETTINGS_KEY must be a valid urlsafe-base64 Fernet key") from exc
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

    @model_validator(mode="after")
    def _validate_files_s3_configured(self) -> "Settings":
        # No storage fallback exists (M18-files.md §3): a deployment without a
        # bucket must refuse to boot, not fail on its first upload.
        if (
            not self.files_s3_bucket
            or not self.files_s3_access_key_id.get_secret_value()
            or not self.files_s3_secret_access_key.get_secret_value()
        ):
            raise ValueError(
                "DISP_FILES_S3_BUCKET, DISP_FILES_S3_ACCESS_KEY_ID and "
                "DISP_FILES_S3_SECRET_ACCESS_KEY are required (M18-files.md §3)"
            )
        return self

    @model_validator(mode="after")
    def _validate_llm_configured(self) -> "Settings":
        if self.llm_enabled and not self.llm_api_key.get_secret_value():
            raise ValueError("DISP_LLM_API_KEY is required when DISP_LLM_ENABLED=true")
        return self

    @model_validator(mode="after")
    def _validate_embedding_configured(self) -> "Settings":
        if (
            self.embedding_enabled
            and self.embedding_provider == "voyage"
            and not self.embedding_api_key.get_secret_value()
        ):
            raise ValueError(
                "DISP_EMBEDDING_API_KEY is required when DISP_EMBEDDING_ENABLED=true "
                "and DISP_EMBEDDING_PROVIDER=voyage"
            )
        return self

    @model_validator(mode="after")
    def _validate_translation_configured(self) -> "Settings":
        # Provider-conditional, like _validate_embedding_configured above: the
        # `fake` backend needs no credential, so a hermetic dev or test
        # deployment can set DISP_TRANSLATION_ENABLED=true without inventing
        # one (M22-translation.md §3).
        if (
            self.translation_enabled
            and self.translation_backend == "deepl"
            and not self.translation_api_key.get_secret_value()
        ):
            raise ValueError(
                "DISP_TRANSLATION_API_KEY is required when DISP_TRANSLATION_ENABLED=true "
                "and DISP_TRANSLATION_BACKEND=deepl"
            )
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
