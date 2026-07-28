from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. No secret is ever hardcoded — everything comes from .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Database ---
    database_url: str = "postgresql+asyncpg://knowveris:knowveris@postgres:5432/knowveris"

    # --- Keycloak ---
    keycloak_url: str = "http://localhost:8080"
    # Server-to-server base (Admin REST API + service-account token). The API
    # reaches Keycloak over the docker network, not the browser-facing host.
    keycloak_internal_url: str = "http://keycloak:8080"
    keycloak_realm: str = "knowveris"
    keycloak_issuer: str = "http://localhost:8080/realms/knowveris"
    keycloak_jwks_url: str = "http://keycloak:8080/realms/knowveris/protocol/openid-connect/certs"
    keycloak_audience: str = "knowveris-api"
    keycloak_admin_client_id: str = "knowveris-admin-cli"
    keycloak_admin_client_secret: str = ""

    # --- Ollama ---
    ollama_url: str = "http://ollama:11434"
    ollama_generation_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    ollama_fallback_model: str = "qwen3:1.7b"
    ollama_embedding_model: str = "bge-m3"
    ollama_num_thread: int = 8
    ollama_num_ctx: int = 4096
    # Cap on generated tokens. -1 = unlimited (Ollama default, off). Generation
    # dominates CPU latency, so a cap (~256) is the main lever — but it changes
    # the answer, so it stays off until measured on the golden set (Week 2).
    ollama_num_predict: int = -1

    # --- RAG (CPU-constrained, see PLAN.md §5) ---
    chunk_size: int = 500
    chunk_overlap: int = 80
    retrieval_top_k: int = 20
    rerank_top_k: int = 3
    # Guardrail 1: refuse before the LLM when the best cosine similarity is below
    # this. Calibrated on the bootstrap golden set (Week 2 D2): 0.50 gives 100%
    # correct-refusal at 7% false-refusal; 0.35 gave 0% correct-refusal (bge-m3
    # scores unrelated questions ~0.4-0.5). Applied to cosine, not the reranker.
    relevance_threshold: float = 0.50
    reranker_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # --- API ---
    api_cors_origins: str = "http://localhost:5173"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    storage_path: str = "/app/storage"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
