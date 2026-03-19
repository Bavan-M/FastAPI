import sys,os
from pathlib import Path
from fastapi import FastAPI
from pydantic_settings import BaseSettings
from pydantic import Field,field_validator
from typing import Optional
from functools import lru_cache

app=FastAPI(title="Secret Management Demo")

class Settings(BaseSettings):
    # App settings
    app_name:str="GEN AI API"
    environment:str=Field(default="development",alias="ENV")
    debug:bool=False

    # Security — REQUIRED, no defaults
    # If missing from .env → app refuses to start
    secret_key:str=Field(...,min_length=32)
    refresh_secret_key:str=Field(...,min_length=32)

    # Database
    database_url:str=Field(default="sqlite:///./dev.db")
    redis_url:str=Field(default="redis://localhost:6379")

    # AI providers — optional, only needed if feature is used
    openai_api_key:Optional[str]=None
    anthropic_api_key:Optional[str]=None
    google_client_id:Optional[str]=None
    google_client_secret:Optional[str]=None

    # Auth config
    access_token_expire_minutes:int=30
    refresh_token_expire_days:int=7
    bcrypt_rounds:int=12

    # Vector DB
    qdrant_url:str=Field(default="http://localhost:6333")
    qdrant_api_key:Optional[str]=None

    # Cors
    allowed_origins:str="http://localhost:3000,http://localhost:5173"

    @field_validator("secret_key","refresh_secret_key")
    @classmethod
    def validate_secret_strength(cls,v:str)->str:
        if v=="changeme" or v=="your-secret-key":
            raise ValueError("Please use a strong,unique secret key")
        if len(v)<32:
            raise ValueError("Secret key must be at least 32 characters")
        
        return v
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls,v:str)->str:
        allowed=["development","staging","production"]
        if v not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v
    
    @property
    def is_production(self)->bool:
        return self.environment=="production"
    
    @property
    def allowed_origins_list(self)->list:
        return [o.strip() for o in self.allowed_origins.split(",")]
    
    class Config: #inbuilt pydantic class to read .env file
        env_file = Path(__file__).parent / ".env"
        env_file_encoding = "utf-8"  # Changed from "utf-8"
        case_sensitive = False

@lru_cache()
def get_settings()->Settings:
    return Settings()

@app.get("/config/info")
def config_info():
    settings=get_settings()
    return {
        "app_name":settings.app_name,
        "environment":settings.environment,
        "is_production":settings.is_production,
        "debug":settings.debug,
        "allowed_origins":settings.allowed_origins,
        "secrets_configured":
        {
            "secret_key":settings.secret_key,
            "openai_key":settings.openai_api_key,
            "anthropic_key":settings.anthropic_api_key,
            "google_auth":settings.google_client_id
        }
    }










