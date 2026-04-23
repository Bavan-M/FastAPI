import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from enum import Enum
from pydantic_settings import BaseSettings,SettingsConfigDict
from pydantic import Field,SecretStr,field_validator,model_validator # field_validator -> checks one field model_validator -> checks multiple fields
from typing import Optional
from functools import lru_cache

class Environment(str,Enum):
    DEVELOPMENT="development"
    STAGING="staging"
    PRODUCTION="production"

# ============================================================
# SETTINGS CLASS
# ============================================================
class Settings(BaseSettings):
    """
    All application configuration in one place.
    Loaded from environment variables and .env file.
    Validated at startup — wrong values crash immediately.
    """

    # --- App ---
    app_name:str="Gen AI app"
    version:str="1.0.0"
    enviroment:Environment=Environment.DEVELOPMENT
    debug:bool=False
    api_prefix:str="/api"

    # --- Security ---
    # Field(...) means REQUIRED — app won't start without it
    # SecretStr prevents value from appearing in logs/repr
    secret_key:SecretStr=Field(...,min_length=32)
    refresh_secret_key:SecretStr=Field(...,min_length=32)
    algorithm:str="HS256"
    access_token_expire_minutes:int=30
    refresh_token_expire_days:int=7

    # --- Database ---
    database_url:str="sqlite+aiosqlite:///./dev.db"
    db_pool_size:int=Field(default=10,ge=1,le=100)
    db_max_overflow:int=Field(default=20,ge=0,le=100)
    db_pool_recycle:int=3600

    # --- Redis ---
    redis_url:str="redis://localhost:6379"
    redis_max_connections:int=50

    # --- MongoDB ---
    mongodb_url:str="mongodb://localhost:27017"
    mongo_db:str="genai_db"

    # --- LLM ---
    openai_api_key:Optional[SecretStr]=None
    anthropic_api_key:Optional[SecretStr]=None
    default_llm_model:str="gpt-4"
    llm_timeout:float=Field(default=45.0,gt=0)
    llm_max_retries:int=Field(default=3,ge=1,le=10)

    # --- Vector DB ---
    qdrant_url:str="http://localhost:6333"
    qdrant_api_key:Optional[SecretStr]=None
    qdrant_collection:str="documents"

    # --- CORS ---
    # Stored as comma-separated string in .env
    # "http://localhost:3000,https://myapp.com"
    allowed_origins_str:str=Field(default="http://localhost:3000,http://localhost:5173",alias="ALLOWED_ORIGINS")

    # --- Rate Limiting ---
    rate_limit_per_minute:int=60
    rate_limit_burst:int=10

    # --- Logging ---
    log_level:str="INFO"
    log_format:str="json"

    # --- Feature Flags ---
    enable_streaming:bool=True
    enable_rag:bool=True
    enable_vector_search:bool=True
    maintenance_mode:bool=True

    # ============================================================
    # VALIDATORS
    # ============================================================

    @field_validator("secret_key","refresh_secret_key",mode="before")
    @classmethod
    def validate_secret_strength(cls,v)->str:
        val=v.get_secret_value() if hasattr(v,"get_secret_value") else str(v)
        if val in ("changeme","your-secret-key","secret"):
            raise ValueError("Please use a strong secret unique key")
        return v
    
    @field_validator("environment",mode="before")
    @classmethod
    def validate_environment(cls,v)->str:
        allowed=[e.value for e in Environment]
        if str(v).lower() not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return str(v).lower()
    
    @field_validator("log_level",mode="before")
    @classmethod
    def validate_log_levels(cls,v)->str:
        allowed=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        val=str(v).upper()
        if val not in allowed:
            raise ValueError(f"Log level must be one of {allowed}")
        return val
    
    @model_validator(mode="after")
    def validate_production_settings(self)->"Settings":
        """Extra validation rules for production environment"""
        if self.enviroment==Environment.PRODUCTION:
            if self.debug:
                raise ValueError("DEBUG must be False in production")
            if not self.openai_api_key and not self.anthropic_api_key:
                raise ValueError("At least one LLM API key required in production")
            if "sqlite" in self.database_url:
                raise ValueError("SQLite not allowed in production — use PostgreSQL")
        return self
    


    # ============================================================
    # COMPUTED PROPERTIES
    # ============================================================
    @property
    def allowed_origins(self)->list[str]:
        return [origin.strip() for origin in self.allowed_origins_str.split(",")]
    
    @property
    def is_production(self)->bool:
        return self.enviroment==Environment.PRODUCTION
    
    @property
    def is_development(self)->bool:
        return self.enviroment==Environment.DEVELOPMENT
    
    @property
    def openai_key(self)->Optional[str]:
        """Get OpenAI key as plain string safely"""
        if self.openai_api_key:
            return self.openai_api_key.get_secret_value()
        return None
    
    @property
    def anthropic_key(self)->Optional[str]:
        if self.anthropic_api_key:
            return self.anthropic_api_key.get_secret_value()
        return None
    
    @property
    def db_url_sync(self)->str:
        """Sync DB URL for Alembic migrations"""
        return self.database_url.replace("+asyncpg","").replace("+aiosqlite","")
    

    
    # ============================================================
    # PYDANTIC SETTINGS CONFIG
    # ============================================================
    model_config=SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True
    )

# ============================================================
# SINGLETON — loaded once, reused everywhere
# ============================================================
@lru_cache()
def get_settings()->Settings:
    """
    Cache settings after first load.
    Calling get_settings() 1000 times = reads .env only once.
    In tests: call get_settings.cache_clear() to reload.
    """
    return Settings()


settings=get_settings()

# ============================================================
# ENVIRONMENT-SPECIFIC CONFIG
# ============================================================
class DevelopmentConfig:
    """Extra dev-only config — debug tools, verbose logging"""
    RELOAD=True
    WORKERS=1
    LOG_LEVEL="DEBUG"
    SHOW_SQL=True
    MOCK_LLM=True

class StagingConfig:
    RELOAD          = False
    WORKERS         = 2
    LOG_LEVEL       = "INFO"
    SHOW_SQL        = False
    MOCK_LLM        = False


class ProductionConfig:
    RELOAD          = False
    WORKERS         = 4        # match CPU cores
    LOG_LEVEL       = "WARNING"
    SHOW_SQL        = False
    MOCK_LLM        = False


ENV_CONFIGS={
    Environment.DEVELOPMENT:DevelopmentConfig,
    Environment.STAGING:StagingConfig,
    Environment.PRODUCTION:ProductionConfig
}

def get_env_config():
    return ENV_CONFIGS[settings.enviroment]


# ============================================================
# .env TEMPLATE — generate this for new developers
# ============================================================

ENV_TEMPLATE = """
# ============================================================
# Application Configuration
# Copy this to .env and fill in your values
# NEVER commit .env to git
# ============================================================

# App
ENV=development
DEBUG=false
APP_NAME=Gen AI API
VERSION=1.0.0

# Security
# Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY=your-32-char-secret-key-here-change-this
REFRESH_SECRET_KEY=your-32-char-refresh-key-here-change-this

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/genai_db

# Redis
REDIS_URL=redis://localhost:6379

# MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB=genai_db

# LLM Providers
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key

# Vector DB
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your-qdrant-key

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Feature Flags
ENABLE_STREAMING=true
ENABLE_RAG=true
MAINTENANCE_MODE=false
"""

# Write template on first run
if not os.path.exists(".env.example"):
    with open(".env.example", "w") as f:
        f.write(ENV_TEMPLATE)
    print("✅ .env.example created — copy to .env and fill in values")


# ============================================================
# SETTINGS IN FASTAPI
# ============================================================

from fastapi import FastAPI, Depends

def get_settings_dependency() -> Settings:
    """FastAPI dependency version of get_settings"""
    return get_settings()


app = FastAPI(title=settings.app_name, version=settings.version)


@app.get("/config/info")
def config_info(s: Settings = Depends(get_settings_dependency)):
    """
    Show non-sensitive config info.
    NEVER expose secrets — show only whether they're set.
    """
    return {
        "app_name":    s.app_name,
        "version":     s.version,
        "environment": s.environment,
        "debug":       s.debug,
        "features": {
            "streaming":     s.enable_streaming,
            "rag":           s.enable_rag,
            "maintenance":   s.maintenance_mode,
        },
        "secrets_configured": {
            "openai":    bool(s.openai_api_key),
            "anthropic": bool(s.anthropic_api_key),
            "qdrant":    bool(s.qdrant_api_key),
        },
        "limits": {
            "rate_limit_per_minute": s.rate_limit_per_minute,
            "llm_timeout":           s.llm_timeout,
        }
    }


@app.get("/config/validate")
def validate_config(s: Settings = Depends(get_settings_dependency)):
    """Check config health — call this in your CI/CD pipeline"""
    issues   = []
    warnings = []

    if not s.openai_api_key and not s.anthropic_api_key:
        warnings.append("No LLM API keys configured — LLM features disabled")
    if s.is_production and s.debug:
        issues.append("DEBUG=true in production — security risk")
    if "localhost" in s.redis_url and s.is_production:
        warnings.append("Redis pointing to localhost in production")
    if "sqlite" in s.database_url and not s.is_development:
        issues.append("SQLite not suitable for non-development environments")
    if s.maintenance_mode:
        warnings.append("Maintenance mode is ON — API returning 503 to users")

    return {
        "status":   "error" if issues else "warning" if warnings else "healthy",
        "issues":   issues,
        "warnings": warnings,
        "environment": s.environment
    }







