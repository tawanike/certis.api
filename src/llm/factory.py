from __future__ import annotations

from typing import TYPE_CHECKING

from src.config import settings

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings
    from langchain_core.language_models.chat_models import BaseChatModel

# Valid provider identifiers
VALID_PROVIDERS = ("ollama", "openai", "azure_openai", "anthropic", "azure_foundry")
EMBEDDING_PROVIDERS = ("ollama", "openai", "azure_openai")

# Module-level caches — cleared when settings change via the API
_llm_cache: dict[str, BaseChatModel] = {}
_embedding_cache: dict[str, Embeddings] = {}
_config_overrides: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Override management (called by LLMSettingsService)
# ---------------------------------------------------------------------------

def load_config_overrides(overrides: dict[str, str]) -> None:
    """Replace the in-memory config overrides and clear all cached instances."""
    _config_overrides.clear()
    _config_overrides.update(overrides)
    clear_llm_cache()


def clear_llm_cache() -> None:
    """Drop all cached LLM / embedding instances so they're recreated on next call."""
    _llm_cache.clear()
    _embedding_cache.clear()


def _get(key: str, fallback: str) -> str:
    """Return config override if set, else the env-based fallback."""
    return _config_overrides.get(key) or fallback


# ---------------------------------------------------------------------------
# Internal constructors (lazy imports to avoid hard dep on unused packages)
# ---------------------------------------------------------------------------

def _create_chat_model(
    provider: str,
    *,
    ollama_model: str,
    openai_model: str,
    azure_openai_model: str,
    anthropic_model: str,
    azure_foundry_model: str,
    temperature: float,
    json_mode: bool = False,
) -> BaseChatModel:
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        kwargs: dict = dict(
            base_url=settings.OLLAMA_BASE_URL,
            model=ollama_model,
            temperature=temperature,
        )
        if json_mode:
            kwargs["format"] = "json"
        return ChatOllama(**kwargs)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if not settings.OPENAI_API_KEY and not _config_overrides.get("openai_api_key"):
            raise ValueError("OPENAI_API_KEY is required when using the openai provider")
        kwargs = dict(
            model=openai_model,
            temperature=temperature,
            api_key=_config_overrides.get("openai_api_key") or settings.OPENAI_API_KEY,
        )
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)

    if provider == "azure_openai":
        from langchain_openai import AzureChatOpenAI

        api_key = _config_overrides.get("azure_openai_api_key") or settings.AZURE_OPENAI_API_KEY
        endpoint = _config_overrides.get("azure_openai_endpoint") or settings.AZURE_OPENAI_ENDPOINT
        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY is required when using the azure_openai provider")
        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is required when using the azure_openai provider")
        kwargs = dict(
            azure_deployment=azure_openai_model,
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            temperature=temperature,
        )
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return AzureChatOpenAI(**kwargs)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not settings.ANTHROPIC_API_KEY and not _config_overrides.get("anthropic_api_key"):
            raise ValueError("ANTHROPIC_API_KEY is required when using the anthropic provider")
        return ChatAnthropic(
            model=anthropic_model,
            temperature=temperature,
            api_key=_config_overrides.get("anthropic_api_key") or settings.ANTHROPIC_API_KEY,
        )

    if provider == "azure_foundry":
        from langchain_anthropic import ChatAnthropic as _ChatAnthropic

        api_key = _config_overrides.get("azure_foundry_api_key") or settings.AZURE_FOUNDRY_API_KEY
        endpoint = _config_overrides.get("azure_foundry_endpoint") or settings.AZURE_FOUNDRY_ENDPOINT
        if not api_key:
            raise ValueError("AZURE_FOUNDRY_API_KEY is required when using the azure_foundry provider")
        if not endpoint:
            raise ValueError("AZURE_FOUNDRY_ENDPOINT is required when using the azure_foundry provider")
        return _ChatAnthropic(
            model=azure_foundry_model,
            temperature=temperature,
            anthropic_api_key=api_key,
            anthropic_api_url=endpoint,
        )

    raise ValueError(f"Unknown provider: {provider!r}. Valid: {VALID_PROVIDERS}")


def _create_embeddings(provider: str) -> Embeddings:
    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        model = _get("model_embedding", settings.OLLAMA_MODEL_EMBEDDING)
        return OllamaEmbeddings(base_url=settings.OLLAMA_BASE_URL, model=model)

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        if not settings.OPENAI_API_KEY and not _config_overrides.get("openai_api_key"):
            raise ValueError("OPENAI_API_KEY is required when using openai embeddings")
        model = _get("model_embedding", settings.OPENAI_MODEL_EMBEDDING)
        return OpenAIEmbeddings(
            model=model,
            api_key=_config_overrides.get("openai_api_key") or settings.OPENAI_API_KEY,
        )

    if provider == "azure_openai":
        from langchain_openai import AzureOpenAIEmbeddings

        api_key = _config_overrides.get("azure_openai_api_key") or settings.AZURE_OPENAI_API_KEY
        endpoint = _config_overrides.get("azure_openai_endpoint") or settings.AZURE_OPENAI_ENDPOINT
        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY is required when using azure_openai embeddings")
        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is required when using azure_openai embeddings")
        model = _get("model_embedding", settings.AZURE_OPENAI_MODEL_EMBEDDING)
        return AzureOpenAIEmbeddings(
            azure_deployment=model,
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )

    if provider in ("anthropic", "azure_foundry"):
        raise ValueError(f"Embeddings are not supported with the {provider!r} provider. Use ollama, openai, or azure_openai.")

    raise ValueError(f"Unknown embedding provider: {provider!r}. Valid: {EMBEDDING_PROVIDERS}")


# ---------------------------------------------------------------------------
# Public factory functions
# ---------------------------------------------------------------------------

def get_primary_llm() -> BaseChatModel:
    """Primary Reasoning Engine. Used for: Claims, Risk, Spec, QA, Intent."""
    key = "primary"
    if key not in _llm_cache:
        provider = _get("provider_primary", settings.LLM_PROVIDER_PRIMARY)
        _llm_cache[key] = _create_chat_model(
            provider,
            ollama_model=_get("model_primary", settings.OLLAMA_MODEL_PRIMARY),
            openai_model=_get("model_primary", settings.OPENAI_MODEL_PRIMARY),
            azure_openai_model=_get("model_primary", settings.AZURE_OPENAI_MODEL_PRIMARY),
            anthropic_model=_get("model_primary", settings.ANTHROPIC_MODEL_PRIMARY),
            azure_foundry_model=_get("model_primary", settings.AZURE_FOUNDRY_MODEL_PRIMARY),
            temperature=0.1,
            json_mode=True,
        )
    return _llm_cache[key]


def get_chat_llm() -> BaseChatModel:
    """Chat Engine. Used for: Conversational Chat stream."""
    key = "chat"
    if key not in _llm_cache:
        provider = _get("provider_chat", settings.LLM_PROVIDER_CHAT)
        _llm_cache[key] = _create_chat_model(
            provider,
            ollama_model=_get("model_chat", settings.OLLAMA_MODEL_CHAT),
            openai_model=_get("model_chat", settings.OPENAI_MODEL_CHAT),
            azure_openai_model=_get("model_chat", settings.AZURE_OPENAI_MODEL_CHAT),
            anthropic_model=_get("model_chat", settings.ANTHROPIC_MODEL_CHAT),
            azure_foundry_model=_get("model_chat", settings.AZURE_FOUNDRY_MODEL_CHAT),
            temperature=0.4,
        )
    return _llm_cache[key]


def get_secondary_llm() -> BaseChatModel:
    """Secondary/Fallback Engine. Used for: Retries, rewrites, fast edits."""
    key = "secondary"
    if key not in _llm_cache:
        provider = _get("provider_secondary", settings.LLM_PROVIDER_SECONDARY)
        _llm_cache[key] = _create_chat_model(
            provider,
            ollama_model=_get("model_secondary", settings.OLLAMA_MODEL_SECONDARY),
            openai_model=_get("model_secondary", settings.OPENAI_MODEL_SECONDARY),
            azure_openai_model=_get("model_secondary", settings.AZURE_OPENAI_MODEL_SECONDARY),
            anthropic_model=_get("model_secondary", settings.ANTHROPIC_MODEL_SECONDARY),
            azure_foundry_model=_get("model_secondary", settings.AZURE_FOUNDRY_MODEL_SECONDARY),
            temperature=0.2,
        )
    return _llm_cache[key]


def get_vision_llm() -> BaseChatModel:
    """Vision Engine. Used for: Parsing diagrams, charts, flowcharts in briefs."""
    key = "vision"
    if key not in _llm_cache:
        provider = _get("provider_vision", settings.LLM_PROVIDER_VISION)
        _llm_cache[key] = _create_chat_model(
            provider,
            ollama_model=_get("model_vision", settings.OLLAMA_MODEL_VISION),
            openai_model=_get("model_vision", settings.OPENAI_MODEL_VISION),
            azure_openai_model=_get("model_vision", settings.AZURE_OPENAI_MODEL_VISION),
            anthropic_model=_get("model_vision", settings.ANTHROPIC_MODEL_VISION),
            azure_foundry_model=_get("model_vision", settings.AZURE_FOUNDRY_MODEL_VISION),
            temperature=0.0,
        )
    return _llm_cache[key]


def get_suggestions_llm() -> BaseChatModel:
    """Suggestions Engine. Used for: Generating contextual suggested actions."""
    key = "suggestions"
    if key not in _llm_cache:
        provider = _get("provider_suggestions", settings.LLM_PROVIDER_SUGGESTIONS)
        _llm_cache[key] = _create_chat_model(
            provider,
            ollama_model=_get("model_suggestions", settings.OLLAMA_MODEL_SUGGESTIONS),
            openai_model=_get("model_suggestions", settings.OPENAI_MODEL_SUGGESTIONS),
            azure_openai_model=_get("model_suggestions", settings.AZURE_OPENAI_MODEL_SUGGESTIONS),
            anthropic_model=_get("model_suggestions", settings.ANTHROPIC_MODEL_SUGGESTIONS),
            azure_foundry_model=_get("model_suggestions", settings.AZURE_FOUNDRY_MODEL_SUGGESTIONS),
            temperature=0.3,
            json_mode=True,
        )
    return _llm_cache[key]


def get_embeddings() -> Embeddings:
    """Embedding Engine. Used for: RAG, Case Law, Prior Art."""
    key = "embedding"
    if key not in _embedding_cache:
        provider = _get("provider_embedding", settings.LLM_PROVIDER_EMBEDDING)
        _embedding_cache[key] = _create_embeddings(provider)
    return _embedding_cache[key]
