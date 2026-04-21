import os,sys
from pathlib import Path
CONFIG_DIR=Path(__file__).parent
PROJECT_ROOT=CONFIG_DIR.parent
sys.path.insert(0,str(PROJECT_ROOT))

from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache

class Settings(BaseSettings):
    app_name:str="Gen AI Streaming app"
    version:str="1.0.0"

    secret_key:str="super-secret-key-change-in-production-32chars"
    algorithm:str="HS256"
    token_expire_minutes:int=60

    openai_api_key:Optional[str]=None
    groq_api_key:Optional[str]=None
    openai_default_model:Optional[str]=None
    groq_default_model:Optional[str]=None

    llm_timeout:float=45.0

    max_retry_attempts:int=3
    retry_base_delay:float=0.5

    cb_failure_threshold:int=3
    cb_recovery_timeout:float=30.0

    max_message_history:int=50
    max_rooms:int=100
    max_room_members:int=50

    class Config:
        env_file=PROJECT_ROOT/".env"
        env_file_encoding="utf-8"
        case_sensitive=False

@lru_cache()
def get_settings()->Settings:
    return Settings()

settings=get_settings()

