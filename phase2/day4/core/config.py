from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name:str="Gen AI API"
    version:str="0.1.0"
    debug:bool=True
    api_prefix:str="/api/v1"

    default_model:str="gpt-4"
    default_temperature:float=0.7
    max_tokens:int=512

    secret_key:str="dev-secret-key-change-in-production"
    token_expire_minutes:int=60

    class Config:
        env_file=".env"

settings=Settings()