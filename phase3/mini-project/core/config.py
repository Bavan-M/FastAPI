import os,sys
from pathlib import Path
# Get the directory containing this config file
CONFIG_DIR = Path(__file__).parent
# Go up one level to get project root
PROJECT_ROOT = CONFIG_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache

class Settings(BaseSettings):
    app_name:str="Multi Role Auth Services"
    version:str="1.0.0"
    environment:str=Field(default="development",alias="ENV")
    debug:bool=False

    secret_key:str=Field(...,min_length=32)
    refresh_secret_key:str=Field(...,min_length=32)
    algorithm:str="HS256"
    access_token_expire_minutes:int=30
    refresh_token_expire_days:int=7

    max_login_attepmts:int=5
    lockout_duration_minutes:int=15

    openai_api_key:Optional[str]=None
    anthropic_api_key:Optional[str]=None

    google_client_id:Optional[str]=None
    google_client_secret:Optional[str]=None
    google_redirect_url:Optional[str]="http://localhost:8000/auth/google/callback"

    allowed_origins:Optional[str]="http://localhost:3000,http://localhost:5173"

    @property
    def allowed_origin_list(self)->list:
        return [o.strip() for o in self.allowed_origins.split(",")]
    
    @property
    def is_production(self)->bool:
        return self.environment=="production"
    
    class Config:
        env_file=PROJECT_ROOT/".env"
        env_file_encoding="utf-8"
        case_sensitive=False


@lru_cache()
def get_settings()->Settings:
    return Settings()

settings=get_settings()
