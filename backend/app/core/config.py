"""Application configuration — loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application
    app_name: str = "Atheria"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    # Local prototype default: file-backed SQLite so the stack runs with no
    # containers and nothing deployed. Point ATHERIA_DATABASE_URL at Postgres
    # (postgresql+asyncpg://...) when that becomes available.
    database_url: str = "sqlite+aiosqlite:///./atheria.db"
    database_echo: bool = False

    # --- LLM provider selection -------------------------------------------
    # "bedrock" works today. "gemini" is implemented and switchable via this
    # single setting once the Google AI Studio endpoint is reachable
    # (currently blocked by the corporate firewall on this network).
    llm_provider: str = "bedrock"
    llm_max_tokens: int = 2000
    llm_temperature: float = 0.0

    # AWS Bedrock
    aws_region: str = "ap-south-1"
    # NOTE: must be an inference-profile ID. Bare model IDs such as
    # "amazon.nova-lite-v1:0" are rejected for on-demand invocation.
    #
    # Nova Lite (~$0.06/$0.24 per 1M) is the cheapest model that reliably
    # honours the full triage schema. Nova Micro is cheaper still but silently
    # omits the flat fields (content_type, product_names, event_terms,
    # seriousness_signal), which breaks triage — verified against the live API.
    bedrock_model_id: str = "apac.amazon.nova-lite-v1:0"
    bedrock_guardrail_id: str | None = None
    bedrock_guardrail_version: str | None = None

    # Google AI Studio (Gemini) — used when llm_provider == "gemini"
    gemini_api_key: str | None = None
    gemini_model_id: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # --- Evidence vault ----------------------------------------------------
    # Open-source storage only. "filesystem" needs nothing installed;
    # "s3" targets MinIO (S3-compatible, self-hosted) via evidence_endpoint_url.
    evidence_backend: str = "filesystem"  # filesystem | s3
    evidence_root: str = "./evidence_vault"
    evidence_bucket: str = "atheria-evidence"
    evidence_endpoint_url: str | None = None  # e.g. http://localhost:9000 (MinIO)
    evidence_access_key: str | None = None
    evidence_secret_key: str | None = None

    # Auth — dev bypass today; Keycloak (open source) is the intended upgrade.
    auth_mode: str = "dev_bypass"  # dev_bypass | oidc
    oidc_issuer_url: str | None = None
    oidc_audience: str | None = None

    # --- Literature intake (NCBI PubMed E-utilities) ------------------------
    # Free without a key; a key raises the rate limit from 3/s to 10/s.
    ncbi_api_key: str | None = None
    ncbi_tool_email: str | None = None

    # Prompts directory (versioned YAML)
    prompts_dir: str = "backend/prompts"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json | console

    model_config = {"env_prefix": "ATHERIA_", "env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
