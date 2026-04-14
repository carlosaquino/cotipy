from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Cotipy"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: str = "*"

    DATABASE_URL: str = "sqlite+aiosqlite:///./data/cotipy.db"

    CACHE_TTL_SECONDS: int = 300
    SCRAPER_TIMEOUT: float = 15.0
    USER_AGENT: str = "Cotipy/0.1 (cotizaciones-py)"

    ENABLE_BCP: bool = True
    ENABLE_MAXICAMBIOS: bool = True
    ENABLE_CAMBIOS_CHACO: bool = True

    REFRESH_INTERVAL_SECONDS: int = 0  # 0 = disabled

    PORT: int = 8000


settings = Settings()
