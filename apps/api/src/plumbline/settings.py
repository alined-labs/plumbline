"""Runtime settings, from the environment and the repo's .env (nothing reads .env any other
way). Frozen: a new setting needs a brain block, and every key is also in .env.example.

Environment variables win over .env, which is how `make check`, the hub and CI force
replay mode whatever a developer's .env says.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from plumbline.core.types import CacheMode, DemoTier

# The repository root (apps/api/src/plumbline/settings.py is four levels down). An image
# that installs the package elsewhere sets PLUMBLINE_ROOT.
ROOT = Path(os.environ.get("PLUMBLINE_ROOT") or Path(__file__).resolve().parents[4])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["dev", "test", "prod"] = "dev"

    # Local services (compose.yaml). The URL's credentials are the throwaway local ones.
    database_url: str = "postgresql+psycopg://plumbline:plumbline@localhost:5433/plumbline"
    redis_url: str = "redis://localhost:6380/0"
    embed_url: str = "http://localhost:8081"  # TEI serving the embedding model
    rerank_url: str = "http://localhost:8082"  # TEI serving the reranker
    docling_url: str = "http://localhost:5001"  # docling-serve

    # Models.
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    cache_mode: CacheMode = CacheMode.REPLAY
    cache_dir: Path = ROOT / "cache"
    answer_config: str = "A2"  # the evals/configs/ file the API answers with

    # Provider keys: only in .env, never exported in a shell that runs Claude Code.
    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    cohere_api_key: SecretStr | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Serving.
    demo_tier: DemoTier = DemoTier.FULL  # until the settings table holds a value
    admin_token: SecretStr | None = None  # the kill switch and tier route; unset: disabled
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    daily_questions_per_ip: int = Field(default=30, ge=1)
    gemini_daily_cap_usd: float = Field(default=1.0, ge=0)
    anthropic_daily_cap_usd: float = Field(default=1.0, ge=0)
    cohere_daily_cap_usd: float = Field(default=0.5, ge=0)
    stub_delay_ms: int = Field(default=15, ge=0)  # pacing of the seed's stub answer


@lru_cache
def get_settings() -> Settings:
    return Settings()
