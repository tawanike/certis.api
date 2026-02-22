"""
Integration tests for Azure LLM providers.

These tests make REAL API calls to Azure OpenAI and Azure AI Foundry.
They verify that credentials, endpoints, and model deployments are configured correctly.

Run with:
    cd backend && uv run pytest tests/test_llm_providers.py -v
"""

import pytest
from src.config import settings
from src.llm.factory import (
    _create_chat_model,
    _create_embeddings,
    clear_llm_cache,
)


# ---------------------------------------------------------------------------
# Guards — skip if credentials aren't set
# ---------------------------------------------------------------------------

azure_openai_configured = pytest.mark.skipif(
    not settings.AZURE_OPENAI_API_KEY or not settings.AZURE_OPENAI_ENDPOINT,
    reason="AZURE_OPENAI_API_KEY / AZURE_OPENAI_ENDPOINT not set",
)

azure_foundry_configured = pytest.mark.skipif(
    not settings.AZURE_FOUNDRY_API_KEY or not settings.AZURE_FOUNDRY_ENDPOINT,
    reason="AZURE_FOUNDRY_API_KEY / AZURE_FOUNDRY_ENDPOINT not set",
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure each test gets a fresh LLM instance."""
    clear_llm_cache()
    yield
    clear_llm_cache()


# ---------------------------------------------------------------------------
# Azure OpenAI — Chat
# ---------------------------------------------------------------------------

@azure_openai_configured
@pytest.mark.asyncio
async def test_azure_openai_chat():
    """Azure OpenAI chat completion returns a non-empty response."""
    # Note: gpt-5.2-chat only supports temperature=1 (default)
    llm = _create_chat_model(
        "azure_openai",
        ollama_model="",
        openai_model="",
        azure_openai_model=settings.AZURE_OPENAI_MODEL_PRIMARY,
        anthropic_model="",
        azure_foundry_model="",
        temperature=1.0,
    )
    response = await llm.ainvoke("Say hello in exactly three words.")
    assert response.content, "Expected non-empty content from Azure OpenAI"
    print(f"\n[Azure OpenAI] {response.content}")


@azure_openai_configured
@pytest.mark.asyncio
async def test_azure_openai_json_mode():
    """Azure OpenAI returns valid JSON when json_mode is enabled."""
    import json

    # Note: gpt-5.2-chat only supports temperature=1 (default)
    llm = _create_chat_model(
        "azure_openai",
        ollama_model="",
        openai_model="",
        azure_openai_model=settings.AZURE_OPENAI_MODEL_PRIMARY,
        anthropic_model="",
        azure_foundry_model="",
        temperature=1.0,
        json_mode=True,
    )
    response = await llm.ainvoke(
        'Return a JSON object with keys "greeting" and "language". '
        'Example: {"greeting": "hello", "language": "en"}'
    )
    data = json.loads(response.content)
    assert "greeting" in data
    print(f"\n[Azure OpenAI JSON] {data}")


# ---------------------------------------------------------------------------
# Azure OpenAI — Embeddings
# ---------------------------------------------------------------------------

@azure_openai_configured
@pytest.mark.asyncio
async def test_azure_openai_embeddings():
    """Azure OpenAI embeddings return a vector of expected dimensionality."""
    embeddings = _create_embeddings("azure_openai")
    vectors = await embeddings.aembed_documents(["Patent claim about a widget."])
    assert len(vectors) == 1
    assert len(vectors[0]) > 100, f"Expected high-dimensional vector, got {len(vectors[0])}"
    print(f"\n[Azure OpenAI Embeddings] dim={len(vectors[0])}")


# ---------------------------------------------------------------------------
# Azure AI Foundry (Anthropic) — Chat
# ---------------------------------------------------------------------------

@azure_foundry_configured
@pytest.mark.asyncio
async def test_azure_foundry_chat():
    """Azure Foundry (Anthropic) chat completion returns a non-empty response."""
    llm = _create_chat_model(
        "azure_foundry",
        ollama_model="",
        openai_model="",
        azure_openai_model="",
        anthropic_model="",
        azure_foundry_model=settings.AZURE_FOUNDRY_MODEL_PRIMARY,
        temperature=0.0,
    )
    response = await llm.ainvoke("Say hello in exactly three words.")
    assert response.content, "Expected non-empty content from Azure Foundry"
    print(f"\n[Azure Foundry] {response.content}")


@azure_foundry_configured
@pytest.mark.asyncio
async def test_azure_foundry_structured_output():
    """Azure Foundry (Anthropic) can produce structured JSON via prompting."""
    import json

    llm = _create_chat_model(
        "azure_foundry",
        ollama_model="",
        openai_model="",
        azure_openai_model="",
        anthropic_model="",
        azure_foundry_model=settings.AZURE_FOUNDRY_MODEL_PRIMARY,
        temperature=0.0,
    )
    response = await llm.ainvoke(
        "Return ONLY a JSON object (no markdown, no explanation) with keys "
        '"greeting" and "language". Example: {"greeting": "hello", "language": "en"}'
    )
    content = response.content.strip()
    data = json.loads(content)
    assert "greeting" in data
    print(f"\n[Azure Foundry JSON] {data}")


@azure_foundry_configured
@pytest.mark.asyncio
async def test_azure_foundry_tool_calling():
    """Azure Foundry (Anthropic) supports tool/function calling."""
    from pydantic import BaseModel, Field

    class WeatherQuery(BaseModel):
        """Get weather for a location."""
        city: str = Field(description="City name")
        unit: str = Field(description="Temperature unit: celsius or fahrenheit", default="celsius")

    llm = _create_chat_model(
        "azure_foundry",
        ollama_model="",
        openai_model="",
        azure_openai_model="",
        anthropic_model="",
        azure_foundry_model=settings.AZURE_FOUNDRY_MODEL_PRIMARY,
        temperature=0.0,
    )
    llm_with_tools = llm.bind_tools([WeatherQuery])
    response = await llm_with_tools.ainvoke("What's the weather in Tokyo?")
    assert response.tool_calls, "Expected at least one tool call"
    assert response.tool_calls[0]["name"] == "WeatherQuery"
    assert "city" in response.tool_calls[0]["args"]
    print(f"\n[Azure Foundry Tools] {response.tool_calls[0]}")


# ---------------------------------------------------------------------------
# Cross-provider: verify factory functions wire up correctly
# ---------------------------------------------------------------------------

@azure_foundry_configured
@azure_openai_configured
@pytest.mark.asyncio
async def test_factory_primary_and_embeddings():
    """End-to-end: primary LLM (Foundry) and embeddings (Azure OpenAI) work together."""
    from src.llm.factory import get_primary_llm, get_embeddings

    llm = get_primary_llm()
    emb = get_embeddings()

    # LLM call
    response = await llm.ainvoke("What is a patent claim? Answer in one sentence.")
    assert response.content
    print(f"\n[Factory Primary] {response.content}")

    # Embedding call
    vectors = await emb.aembed_documents([response.content])
    assert len(vectors) == 1
    assert len(vectors[0]) > 100
    print(f"[Factory Embeddings] dim={len(vectors[0])}")
