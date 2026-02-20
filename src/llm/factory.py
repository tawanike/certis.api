from functools import lru_cache
from langchain_ollama import ChatOllama, OllamaEmbeddings
from src.config import settings

@lru_cache()
def get_primary_llm() -> ChatOllama:
    """
    Primary Reasoning Engine (gpt-oss:20b).
    Used for: Claims, Risk, Spec, QA, Intent.
    """
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL_PRIMARY,
        temperature=0.1, # Strict for JSON/Reasoning
        format="json", # Force JSON mode where possible (Ollama specific)
    )

@lru_cache()
def get_chat_llm() -> ChatOllama:
    """
    Chat Engine (deepseek-r1:14b).
    Used for: Conversational Chat stream with explicit thinking tokens.
    """
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model="deepseek-r1:14b",
        temperature=0.4,
    )

@lru_cache()
def get_secondary_llm() -> ChatOllama:
    """
    Secondary/Fallback Engine (gemma3:12b).
    Used for: Retries, rewrites, fast edits.
    """
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL_SECONDARY,
        temperature=0.2,
    )

@lru_cache()
def get_vision_llm() -> ChatOllama:
    """
    Vision Engine (granite3.2-vision).
    Used for: Parsing diagrams, charts, flowcharts in briefs.
    """
    return ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL_VISION,
        temperature=0.0,
    )

@lru_cache()
def get_embeddings() -> OllamaEmbeddings:
    """
    Embedding Engine (embeddinggemma).
    Used for: RAG, Case Law, Prior Art.
    """
    return OllamaEmbeddings(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL_EMBEDDING,
    )
