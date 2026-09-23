from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config= SettingsConfigDict(env_file=".env", extra="ignore")
    DATABASE_URL:str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    MAX_PLAYERS:int
    MIN_PLAYERS:int
    FRONTEND_URL: str | None = None
    REDIS_URL: str | None = None
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_USERNAME: str = "default"
    REDIS_SSL: bool = False
    CACHE_TTL: int = 1800
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30

settings= Settings()