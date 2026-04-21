"""Settings loaded from env (12-factor)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POS_INVENTORY_", env_file=".env", extra="ignore")

    db_dsn: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/pos_inventory",
        description="SQLAlchemy DSN (psycopg3 driver).",
    )
    jwt_public_key: str = Field(
        default="-----BEGIN PUBLIC KEY-----\nDEV-ONLY\n-----END PUBLIC KEY-----",
        description="JWT RS256 public key (PEM). Replace per-tenant in production.",
    )
    jwt_algorithm: str = Field(default="RS256")
    jwt_audience: str | None = Field(default=None)
    webhook_url: str | None = Field(default=None, description="Tenant-default webhook URL for outbox worker.")
    over_receive_tolerance_pct_default: int = Field(default=10)
    auth_bypass: bool = Field(default=False, description="Dev-only: accept unsigned tenant headers.")

    @property
    def db_dsn_sync(self) -> str:
        # Alembic + initial scaffolding use the sync driver
        return self.db_dsn.replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    return Settings()
