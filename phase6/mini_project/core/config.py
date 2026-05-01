import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from typing import Optional
from functools import lru_cache
from pathlib import Path
CONFIG_DIR=Path(__file__).parent
PROJECT_ROOT=CONFIG_DIR.parent
sys.path.insert(0,str(PROJECT_ROOT))


class Settings(BaseSettings):
    # App
    app_name:    str = "Production Gen AI API"
    version:     str = "1.0.0"
    environment: str = Field(default="development", alias="ENV")
    debug:       bool = False

    # Security
    secret_key:         SecretStr = Field(..., min_length=32,alias="SECRET_KEY")
    algorithm:          str       = "HS256"
    token_expire_minutes: int     = 30

    # LLM
    openai_api_key:    Optional[SecretStr] = None
    anthropic_api_key: Optional[SecretStr] = None
    default_model:     str                 = "gpt-4"
    llm_timeout:       float               = 45.0

    # Rate limiting
    rate_limit_per_minute: int = 60
    llm_rate_limit:        int = 10

    # Telemetry
    otel_enabled:        bool = True
    otel_exporter_endpoint: str = "http://localhost:4317"
    prometheus_enabled:  bool = True

    # Logging
    log_level:  str = "INFO"
    log_format: str = "json"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT/".env",
        case_sensitive=False,
        extra="ignore",
        env_file_encoding="utf-8"
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()