from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = "Aurelian Autonomous Enterprise Operations"
    version: str = "0.3.5.2"
    environment: str = os.getenv("APP_ENV", "demo")

    # Database DSNs intentionally omit passwords in the Docker topology.
    # Credentials are mounted as Docker secrets and supplied to asyncpg separately.
    database_url: str = os.getenv("DATABASE_URL", "sqlite:////tmp/aurelian_v35.db")
    database_password_secret: str = os.getenv("DATABASE_PASSWORD_SECRET", "POSTGRES_APP_PASSWORD")
    audit_database_url: str = os.getenv("AUDIT_DATABASE_URL", os.getenv("DATABASE_URL", "sqlite:////tmp/aurelian_v35.db"))
    audit_database_password_secret: str = os.getenv("AUDIT_DATABASE_PASSWORD_SECRET", "POSTGRES_AUDIT_PASSWORD")

    jwt_issuer: str = os.getenv("JWT_ISSUER", "aurelian-demo")
    jwt_audience: str = os.getenv("JWT_AUDIENCE", "aurelian-ops")
    oidc_issuer: str = os.getenv("OIDC_ISSUER", "")
    oidc_audience: str = os.getenv("OIDC_AUDIENCE", "")
    oidc_jwks_url: str = os.getenv("OIDC_JWKS_URL", "")

    guard_model_url: str = os.getenv("GUARD_MODEL_URL", "")
    guard_model_name: str = os.getenv("GUARD_MODEL_NAME", "meta-llama/Llama-Guard")
    guard_api_key: str = os.getenv("GUARD_API_KEY", "")

    opa_url: str = os.getenv("OPA_URL", "")
    redis_url: str = os.getenv("REDIS_URL", "")
    redis_password_secret: str = os.getenv("REDIS_PASSWORD_SECRET", "REDIS_PASSWORD")
    qdrant_url: str = os.getenv("QDRANT_URL", "")
    qdrant_api_key_secret: str = os.getenv("QDRANT_API_KEY_SECRET", "QDRANT_API_KEY")
    tool_runner_url: str = os.getenv("TOOL_RUNNER_URL", "")
    planner_url: str = os.getenv("PLANNER_URL", "")
    siem_webhook_url: str = os.getenv("SIEM_WEBHOOK_URL", "")

    otel_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    otel_service_name: str = os.getenv("OTEL_SERVICE_NAME", "aurelian-control-plane-api")

    public_demo: bool = os.getenv("PUBLIC_DEMO", "false").lower() == "true"
    max_workflow_steps: int = int(os.getenv("MAX_WORKFLOW_STEPS", "12"))
    max_tool_retries: int = int(os.getenv("MAX_TOOL_RETRIES", "2"))
    retrieval_threshold: float = float(os.getenv("RETRIEVAL_THRESHOLD", "0.22"))
    recovery_stale_seconds: int = int(os.getenv("RECOVERY_STALE_SECONDS", "300"))
    local_cache_max_entries: int = int(os.getenv("LOCAL_CACHE_MAX_ENTRIES", "512"))


settings = Settings()
