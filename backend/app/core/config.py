"""
Configuration settings for AI Ranker V2
Using Pydantic Settings for environment variable management
"""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """
    
    # Database
    database_url: str = Field(
        "postgresql+asyncpg://user:pass@localhost/airanker",
        description="Async PostgreSQL connection URL"
    )
    database_sync_url: Optional[str] = Field(
        None,
        description="Sync PostgreSQL URL for migrations"
    )
    
    # Phase-1 Configuration (No Redis/Celery)
    execution_mode: str = Field("sync", description="sync or celery")
    use_redis: bool = Field(False, description="Enable Redis")
    use_celery: bool = Field(False, description="Enable Celery")
    
    # API Keys
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    google_cloud_project: str = Field("contestra-ai", description="GCP project")
    vertex_location: str = Field("europe-west4", description="Vertex AI location")
    
    # Server Settings
    host: str = Field("0.0.0.0", description="Server host")
    port: int = Field(8000, description="Server port")
    environment: str = Field("development", description="Environment name")
    log_level: str = Field("info", description="Logging level")
    sql_echo: bool = Field(False, description="Echo SQL queries")
    
    # Security
    secret_key: str = Field(..., description="Secret key for HMAC")
    cors_origins: List[str] = Field(
        ["http://localhost:3000", "http://localhost:3001"],
        description="Allowed CORS origins"
    )
    
    # Immutability Settings
    enforce_model_version: bool = Field(True, description="Enforce model version equality")
    require_grounding_evidence: bool = Field(True, description="Require grounding evidence")
    enable_idempotency: bool = Field(True, description="Enable idempotency checks")
    
    # Provider Version Cache
    provider_version_cache_ttl_seconds: int = Field(
        300,
        description="Provider version cache TTL in seconds"
    )
    
    # ALS Settings
    als_max_length: int = Field(350, description="Maximum ALS block length")
    als_seed_keys: dict = Field(
        default_factory=lambda: {"k1": "default_seed_key"},
        description="ALS seed keys for HMAC"
    )
    default_seed_key_id: str = Field("k1", description="Default ALS seed key ID")
    
    # Batch Execution
    batch_max_size: int = Field(100, description="Maximum batch size")
    batch_rate_limit: int = Field(10, description="Requests per second")
    batch_retry_max: int = Field(3, description="Maximum retries")
    batch_drift_policy: str = Field("fail", description="hard|fail|warn")
    
    # Idempotency
    idempotency_ttl_seconds: int = Field(
        86400,  # 24 hours
        description="Idempotency key TTL"
    )
    
    # ------------------------------
    # OpenAI Rate Limit & Concurrency
    # ------------------------------
    openai_max_concurrency: int = Field(3, description="Max concurrent OpenAI calls")
    openai_stagger_seconds: int = Field(15, description="Stagger between OpenAI launches (seconds)")
    openai_tpm_limit: int = Field(30000, description="OpenAI tokens per minute limit")
    openai_tpm_headroom: float = Field(0.15, description="Headroom fraction to keep under TPM")
    openai_est_tokens_per_run: int = Field(7000, description="Estimated tokens per OpenAI run (in+out)")
    openai_retry_max_attempts: int = Field(5, description="Max attempts on 429 rate limit")
    openai_backoff_base_seconds: int = Field(2, description="Base backoff seconds for 429 (exponential)")
    
    # ------------------------------
    # OpenAI Gating Location
    # ------------------------------
    openai_gate_in_adapter: bool = Field(True,  description="Apply OpenAI rate limiting in adapter")
    openai_gate_in_batch:   bool = Field(False, description="Apply OpenAI rate limiting in batch runner (legacy)")
    
    finalize_lowers_concurrency: bool = Field(True, description="Drop concurrency when finalize bursts happen")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables
        
    def get_als_seed(self, key_id: str) -> str:
        """Get ALS seed key by ID"""
        return self.als_seed_keys.get(key_id, self.als_seed_keys[self.default_seed_key_id])
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.environment.lower() == "development"
    
    @property
    def debug(self) -> bool:
        """Check if in debug mode"""
        return self.is_development


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance"""
    return settings