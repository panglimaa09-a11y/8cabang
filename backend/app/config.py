"""Application configuration — read from environment variables only.

No secrets live in the repo. See CONTRACT.md section 2.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = ""
    JWT_SECRET: str = "dev-only-change-me"
    JWT_EXPIRE_MINUTES: int = 720
    JWT_ALGORITHM: str = "HS256"

    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    BOOTSTRAP_OWNER_EMAIL: str = ""
    BOOTSTRAP_OWNER_PASSWORD: str = ""

    ALLOW_NEGATIVE_STOCK: bool = False
    CORS_ORIGINS: str = "*"
    FRONTEND_DIR: str = "/srv/app"  # dir containing index.html (Docker); local: repo root
    APP_VERSION: str = "2.0.0"
    DB_AUTO_CREATE: bool = False  # dev convenience only; production uses migrations

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
