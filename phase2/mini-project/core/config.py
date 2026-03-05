from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name:str="Task Manager API"
    version:str="1.0.0"
    secret_key:str="super-secret-change-in-production"
    token_expire_minutes:int=60
    api_prefix:str="api/v1"

    class Config:
        env_file=".env"

settings=Settings()
