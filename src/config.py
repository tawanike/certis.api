from typing import List, Union
from pydantic import AnyHttpUrl, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Certis Backend"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/v1"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "https://certis.space",
        "https://www.certis.space",
        "https://app.certis.space",
    ]

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "certis"
    POSTGRES_PORT: int = 5432

    # Auth
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7" # openssl rand -hex 32
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 days

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_PRIMARY: str = "gpt-oss:20b"
    OLLAMA_MODEL_SECONDARY: str = "gemma3:12b"
    OLLAMA_MODEL_CHAT: str = "deepseek-r1:14b"
    OLLAMA_MODEL_EMBEDDING: str = "embeddinggemma"
    OLLAMA_MODEL_VISION: str = "granite3.2-vision"
    OLLAMA_MODEL_SUGGESTIONS: str = "gemma3:12b"

    # OpenAI (direct API)
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL_PRIMARY: str = "gpt-4o"
    OPENAI_MODEL_SECONDARY: str = "gpt-4o-mini"
    OPENAI_MODEL_CHAT: str = "gpt-4o"
    OPENAI_MODEL_VISION: str = "gpt-4o"
    OPENAI_MODEL_SUGGESTIONS: str = "gpt-4o-mini"
    OPENAI_MODEL_EMBEDDING: str = "text-embedding-3-small"

    # Azure OpenAI
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_VERSION: str = "2024-12-01-preview"
    AZURE_OPENAI_MODEL_PRIMARY: str = "gpt-4o"
    AZURE_OPENAI_MODEL_SECONDARY: str = "gpt-4o-mini"
    AZURE_OPENAI_MODEL_CHAT: str = "gpt-4o"
    AZURE_OPENAI_MODEL_VISION: str = "gpt-4o"
    AZURE_OPENAI_MODEL_SUGGESTIONS: str = "gpt-4o-mini"
    AZURE_OPENAI_MODEL_EMBEDDING: str = "text-embedding-3-small"

    # Anthropic (direct API)
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL_PRIMARY: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MODEL_SECONDARY: str = "claude-haiku-4-5-20251001"
    ANTHROPIC_MODEL_CHAT: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MODEL_VISION: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MODEL_SUGGESTIONS: str = "claude-sonnet-4-20250514"

    # Azure AI Foundry (Anthropic models via Azure)
    AZURE_FOUNDRY_API_KEY: str | None = None
    AZURE_FOUNDRY_ENDPOINT: str | None = None
    AZURE_FOUNDRY_MODEL_PRIMARY: str = "claude-sonnet-4-20250514"
    AZURE_FOUNDRY_MODEL_SECONDARY: str = "claude-haiku-4-5-20251001"
    AZURE_FOUNDRY_MODEL_CHAT: str = "claude-sonnet-4-20250514"
    AZURE_FOUNDRY_MODEL_VISION: str = "claude-sonnet-4-20250514"
    AZURE_FOUNDRY_MODEL_SUGGESTIONS: str = "claude-sonnet-4-20250514"

    # Per-role provider selection (ollama | openai | azure_openai | anthropic | azure_foundry)
    LLM_PROVIDER_PRIMARY: str = "ollama"
    LLM_PROVIDER_SECONDARY: str = "ollama"
    LLM_PROVIDER_CHAT: str = "ollama"
    LLM_PROVIDER_VISION: str = "ollama"
    LLM_PROVIDER_SUGGESTIONS: str = "ollama"
    LLM_PROVIDER_EMBEDDING: str = "ollama"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

settings = Settings()
