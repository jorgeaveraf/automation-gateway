from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field("Automation Gateway")
    app_version: str = Field("0.1.0")
    log_level: str = Field("INFO")
    automation_gateway_api_key: SecretStr | None = Field(default=None)
    qbo_gateway_base_url: str | None = Field(default=None)
    qbo_gateway_api_key: SecretStr | None = Field(default=None)
    qbo_gateway_timeout_seconds: float = Field(default=10.0, gt=0)

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings loader to avoid re-parsing environment variables across requests.
    """
    return Settings()
