"""Application configuration (environment variables / backend/.env).

Secrets use SecretStr so they never appear in repr(), logs or error pages.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # --- Sarvam ---------------------------------------------------------
    sarvam_api_key: SecretStr | None = Field(default=None, alias="SARVAM_API_KEY")
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_chat_model: Literal["sarvam-105b"] = "sarvam-105b"
    sarvam_embedding_model: str = "embeddinggemma-2"
    sarvam_timeout_s: float = 35.0
    sarvam_max_retries: int = 2
    # sarvam-105b counts reasoning tokens in max_tokens; with reasoning enabled it can exhaust
    # the budget and return empty content (observed live), so reasoning is off by default.
    sarvam_max_tokens: int = Field(default=900, ge=128, le=4096)
    sarvam_temperature: float = 0.2
    sarvam_reasoning_effort: Literal["none", "low", "medium", "high"] | None = "none"

    # --- Anthropic / inference budgets ----------------------------------
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_chat_model: Literal["claude-haiku-5-5"] = "claude-haiku-5-5"
    anthropic_max_tokens: int = Field(default=900, ge=128, le=4096)
    anthropic_timeout_s: float = 45.0
    anthropic_prompt_cache: bool = Field(
        default=False, validation_alias=AliasChoices("ANTHROPIC_PROMPT_CACHE_ENABLED", "ANTHROPIC_PROMPT_CACHE",
                                                    "anthropic_prompt_cache")
    )
    anthropic_workspace_id: str | None = None
    rag_context_optimization_enabled: bool = False
    faq_cache_enabled: bool = False
    faq_cache_signing_key: SecretStr | None = None
    anthropic_rate_limit_requests: int = Field(default=10, ge=1, le=60)
    general_knowledge_enabled: bool = True
    conversational_answers_enabled: bool = False
    knowledge_enrichment_enabled: bool = False
    official_source_lookup_enabled: bool = False
    knowledge_auto_publish_enabled: bool = False
    context_token_budget: int = Field(default=1800, ge=256, le=12000)
    context_top_k: int = Field(default=3, ge=1, le=10)
    prompt_token_budget: int = Field(default=6000, ge=512, le=16000)
    history_token_budget: int = Field(default=600, ge=64, le=2000)
    rag_expanded_context_token_budget: int = Field(default=3000, ge=256, le=12000)
    rag_expanded_top_k: int = Field(default=10, ge=5, le=20)
    # Configured estimate, not an exchange-rate feed or a billing setting.
    usd_inr_estimate: float = Field(default=85.0, gt=0)
    sarvam_input_inr_million: float = Field(default=10.0, ge=0)
    sarvam_cached_inr_million: float = Field(default=0.25, ge=0)
    sarvam_output_inr_million: float = Field(default=25.0, ge=0)
    anthropic_input_usd_million: float = Field(default=0.10, ge=0)
    anthropic_output_usd_million: float = Field(default=0.50, ge=0)
    anthropic_cache_read_usd_million: float = Field(default=0.01, ge=0)
    api_pricing_version: str = Field(default="2026-11-20-list", max_length=24)
    anthropic_cache_write_1h_usd_million: float = Field(default=0.20, ge=0)
    anthropic_cache_write_usd_million: float = Field(default=0.125, ge=0)

    # --- Knowledge & index ----------------------------------------------
    knowledge_raw_dir: Path = PROJECT_DIR / "knowledge" / "raw"
    knowledge_curated_dir: Path = PROJECT_DIR / "knowledge" / "curated"
    # The deployable, approved-only corpus. The ONLY knowledge input in production.
    knowledge_corpus_dir: Path = PROJECT_DIR / "knowledge" / "deploy"
    approval_manifest: Path = PROJECT_DIR / "knowledge" / "approval_manifest.json"
    index_dir: Path = BACKEND_DIR / "data" / "lancedb"
    index_table: str = "knowledge_chunks"
    # auto: use Sarvam embeddings if the key has access, else lexical. lexical / sarvam force one.
    embedding_provider: Literal["auto", "lexical", "sarvam"] = "auto"

    # --- Retrieval ------------------------------------------------------
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    retrieval_candidates: int = Field(default=30, ge=5, le=200)
    retrieval_min_score: float = 0.15
    retrieval_vector_weight: float = 0.45
    retrieval_max_per_source: int = 2

    # --- API ------------------------------------------------------------
    cors_origins: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]
    max_request_bytes: int = 16_384
    max_message_chars: int = 1000
    max_history_turns: int = 10
    rate_limit_requests: int = 20
    rate_limit_window_s: int = 60
    # Client-IP resolution for rate limiting:
    #  * TRUSTED_PROXY_HOPS=0 (default, local): trust X-Forwarded-For only when the peer is in TRUSTED_PROXIES
    #    (the Next.js proxy on localhost) and use its first entry.
    #  * TRUSTED_PROXY_HOPS=N (deployed behind N proxies that each append to X-Forwarded-For, e.g. Vercel
    #    rewrite + Railway edge = 2): use the N-th entry from the right, which clients cannot spoof.
    trusted_proxies: list[str] = ["127.0.0.1", "::1"]
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    proxy_shared_secret: SecretStr | None = None

    # --- Database (analytics + admin) ------------------------------------
    # SQLite for development; PostgreSQL in production, e.g.
    # postgresql+psycopg://user:pass@host:5432/dbname (requires `psycopg[binary]`).
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}"
    allow_sqlite_in_production: bool = False

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        # Railway/Heroku style URLs -> SQLAlchemy + psycopg 3 driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    # --- Admin authentication -------------------------------------------
    environment: Literal["development", "production"] = "development"
    admin_session_ttl_minutes: int = 480  # absolute lifetime
    admin_session_idle_minutes: int = 60  # sliding inactivity timeout
    admin_login_max_failures: int = 5  # per email+IP within the window
    admin_login_window_minutes: int = 15
    # Browser origins allowed to POST to admin endpoints (login CSRF protection).
    admin_allowed_origins: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]
    # Force the Secure cookie flag; defaults to True automatically in production.
    cookie_secure: bool | None = None

    @property
    def secure_cookies(self) -> bool:
        return self.cookie_secure if self.cookie_secure is not None else self.environment == "production"

    # --- Logging --------------------------------------------------------
    log_level: str = "INFO"
    # Legacy setting retained to reject insecure production configuration.
    log_chat_content: bool = False

    def production_problems(self) -> list[str]:
        """Configuration errors that must block a production start."""
        if self.environment != "production":
            return []
        problems = []
        if self.log_chat_content:
            problems.append("LOG_CHAT_CONTENT must be false in production")
        if self.cookie_secure is False:
            problems.append("COOKIE_SECURE must not be false in production")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must not contain '*'")
        if not self.admin_allowed_origins or all(
            o.startswith(("http://127.0.0.1", "http://localhost")) for o in self.admin_allowed_origins
        ):
            problems.append("ADMIN_ALLOWED_ORIGINS must list the public frontend origin (https://…)")
        if any(o.startswith("http://") for o in self.admin_allowed_origins + self.cors_origins):
            problems.append("Production origins must use https://")
        if self.database_url.startswith("sqlite") and not self.allow_sqlite_in_production:
            problems.append("DATABASE_URL must point to PostgreSQL in production (container disks are ephemeral)")
        return problems

    @property
    def sarvam_configured(self) -> bool:
        return bool(self.sarvam_api_key and self.sarvam_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
