from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(default="", validation_alias="BOT_TOKEN")
    tg_proxy_url: str = Field(default="", validation_alias="TG_PROXY_URL")
    external_proxy_url: str = Field(default="", validation_alias="EXTERNAL_PROXY_URL")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/factcheck",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-haiku-5.5", validation_alias="ANTHROPIC_MODEL")
    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="", validation_alias="OPENROUTER_MODEL")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", validation_alias="OPENROUTER_BASE_URL"
    )
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    max_input_length: int = Field(default=30_000, validation_alias="MAX_INPUT_LENGTH")
    max_text_length: int = Field(default=30_000, validation_alias="MAX_TEXT_LENGTH")
    max_url_length: int = Field(default=2_048, validation_alias="MAX_URL_LENGTH")
    max_download_size: int = Field(default=5_000_000, validation_alias="MAX_DOWNLOAD_SIZE")
    request_timeout: float = Field(default=10.0, validation_alias="REQUEST_TIMEOUT")
    max_redirects: int = Field(default=3, validation_alias="MAX_REDIRECTS")
    max_image_size: int = Field(default=10_000_000, validation_alias="MAX_IMAGE_SIZE")
    content_cache_ttl: int = Field(default=3_600, validation_alias="CONTENT_CACHE_TTL")
    mock_ocr_text: str = Field(default="", validation_alias="MOCK_OCR_TEXT")
    claim_chunk_size: int = Field(default=8_000, validation_alias="CLAIM_CHUNK_SIZE")
    claim_chunk_overlap: int = Field(default=500, validation_alias="CLAIM_CHUNK_OVERLAP")
    max_claim_chunks: int = Field(default=20, validation_alias="MAX_CLAIM_CHUNKS")
    claim_parallelism: int = Field(default=2, validation_alias="CLAIM_PARALLELISM")
    yandex_api_key: str = Field(default="", validation_alias="YANDEX_API_KEY")
    yandex_folder_id: str = Field(default="", validation_alias="YANDEX_FOLDER_ID")
    search_proxy_url: str = Field(default="", validation_alias="SEARCH_PROXY_URL")
    yandex_search_type: str = Field(default="SEARCH_TYPE_RU", validation_alias="YANDEX_SEARCH_TYPE")
    yandex_family_mode: str = Field(
        default="FAMILY_MODE_MODERATE", validation_alias="YANDEX_FAMILY_MODE"
    )
    yandex_response_format: str = Field(
        default="FORMAT_XML", validation_alias="YANDEX_RESPONSE_FORMAT"
    )
    yandex_api_url: str = Field(
        default="https://searchapi.api.cloud.yandex.net/v2/web/search",
        validation_alias="YANDEX_API_URL",
    )
    search_cache_ttl: int = Field(default=900, validation_alias="SEARCH_CACHE_TTL")
    search_timeout: float = Field(default=10.0, validation_alias="SEARCH_TIMEOUT")
    search_results_limit: int = Field(default=8, validation_alias="SEARCH_RESULTS_LIMIT")
    search_max_queries_per_claim: int = Field(
        default=5, validation_alias="SEARCH_MAX_QUERIES_PER_CLAIM"
    )
    search_results_per_query: int = Field(default=8, validation_alias="SEARCH_RESULTS_PER_QUERY")
    search_max_unique_sources: int = Field(default=20, validation_alias="SEARCH_MAX_UNIQUE_SOURCES")
    search_max_sources_per_domain: int = Field(
        default=3, validation_alias="SEARCH_MAX_SOURCES_PER_DOMAIN"
    )
    search_max_passes: int = Field(default=2, validation_alias="SEARCH_MAX_PASSES")
    search_early_stop_min_sources: int = Field(
        default=4, validation_alias="SEARCH_EARLY_STOP_MIN_SOURCES"
    )
    search_parallelism: int = Field(default=3, validation_alias="SEARCH_PARALLELISM")
    top_sources_per_claim: int = Field(default=5, validation_alias="TOP_SOURCES_PER_CLAIM")
    source_fetch_parallelism: int = Field(default=3, validation_alias="SOURCE_FETCH_PARALLELISM")
    evidence_chunk_size: int = Field(default=6_000, validation_alias="EVIDENCE_CHUNK_SIZE")
    evidence_chunk_overlap: int = Field(default=400, validation_alias="EVIDENCE_CHUNK_OVERLAP")
    max_evidence_chunks: int = Field(default=8, validation_alias="MAX_EVIDENCE_CHUNKS")
    max_evidence_text: int = Field(default=24_000, validation_alias="MAX_EVIDENCE_TEXT")
    evidence_parallelism: int = Field(default=3, validation_alias="EVIDENCE_PARALLELISM")
    rate_limit_per_minute: int = Field(default=5, validation_alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_window_seconds: int = Field(default=60, validation_alias="RATE_LIMIT_WINDOW_SECONDS")
    queue_stream: str = Field(default="factcheck:jobs", validation_alias="QUEUE_STREAM")
    queue_group: str = Field(default="factcheck-workers", validation_alias="QUEUE_GROUP")
    queue_block_ms: int = Field(default=5_000, validation_alias="QUEUE_BLOCK_MS")
    job_max_retries: int = Field(default=2, validation_alias="JOB_MAX_RETRIES")
    job_dedupe_ttl: int = Field(default=3_600, validation_alias="JOB_DEDUPE_TTL")
    external_max_retries: int = Field(default=2, validation_alias="EXTERNAL_MAX_RETRIES")
    external_backoff_seconds: float = Field(
        default=0.5, validation_alias="EXTERNAL_BACKOFF_SECONDS"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
