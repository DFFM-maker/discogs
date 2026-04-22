from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_name: str = "LP Monitor"
    secret_key: str = "dev-secret-change-in-production"
    debug: bool = False
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # Database
    database_url: str = "postgresql://lp:lppass@db:5432/lpmonitor"

    # Admin bootstrap
    admin_username: str = "admin"
    admin_email: str = "admin@localhost"
    admin_password: str = "changeme"

    # Discogs
    discogs_token: str = ""
    discogs_user_agent: str = "LPMonitor/1.0 +https://vinylmonitor.dffm.it"

    # Claude
    claude_api_key: str = ""
    claude_enabled: bool = True
    claude_model: str = "claude-sonnet-4-6"
    claude_max_tokens: int = 1024
    claude_timeout_seconds: int = 30

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""
    mail_to: str = ""
    email_enabled: bool = True

    # Scheduler
    scan_interval_minutes: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
