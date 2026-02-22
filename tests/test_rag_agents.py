"""Tests for RAG integration into patent drafting agents."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from src.documents.service import DocumentService
from src.agents.state import AgentState
from src.agents.risk.agent import RiskAgentState
from src.agents.risk.re_evaluation_agent import ReEvalAgentState
from src.agents.spec.agent import SpecAgentState
from src.agents.qa.agent import QAAgentState
from src.drafting.service import DraftingService


# ---------------------------------------------------------------------------
# Unit tests for format_chunks_as_context
# ---------------------------------------------------------------------------

class TestFormatChunksAsContext:
    def test_formats_chunks_correctly(self):
        chunks = [
            {"filename": "patent.pdf", "page_number": 1, "content": "First chunk content"},
            {"filename": "patent.pdf", "page_number": 2, "content": "Second chunk content"},
        ]
        result = DocumentService.format_chunks_as_context(chunks)
        assert "[patent.pdf, Page 1]: First chunk content" in result
        assert "[patent.pdf, Page 2]: Second chunk content" in result
        assert "\n\n---\n\n" in result

    def test_empty_chunks_returns_empty_string(self):
        result = DocumentService.format_chunks_as_context([])
        assert result == ""

    def test_single_chunk_no_separator(self):
        chunks = [{"filename": "doc.pdf", "page_number": 3, "content": "Only chunk"}]
        result = DocumentService.format_chunks_as_context(chunks)
        assert result == "[doc.pdf, Page 3]: Only chunk"
        assert "---" not in result

    def test_missing_fields_use_defaults(self):
        chunks = [{"content": "some text"}]
        result = DocumentService.format_chunks_as_context(chunks)
        assert "[unknown, Page ?]: some text" in result


# ---------------------------------------------------------------------------
# Agent state type tests
# ---------------------------------------------------------------------------

class TestAgentStateTypes:
    def test_agent_state_has_document_context(self):
        assert "document_context" in AgentState.__annotations__

    def test_risk_agent_state_has_document_context(self):
        assert "document_context" in RiskAgentState.__annotations__

    def test_reeval_agent_state_has_document_context(self):
        assert "document_context" in ReEvalAgentState.__annotations__

    def test_spec_agent_state_has_document_context(self):
        assert "document_context" in SpecAgentState.__annotations__

    def test_qa_agent_state_has_document_context(self):
        assert "document_context" in QAAgentState.__annotations__


# ---------------------------------------------------------------------------
# Service _retrieve_document_context tests
# ---------------------------------------------------------------------------

class TestRetrieveDocumentContext:
    @pytest.mark.asyncio
    async def test_returns_formatted_context_when_docs_exist(self):
        mock_db = AsyncMock()
        service = DraftingService(mock_db)

        mock_chunks = [
            {
                "id": str(uuid4()),
                "document_id": str(uuid4()),
                "filename": "invention.pdf",
                "page_number": 1,
                "content": "The invention uses a neural network",
                "token_count": 6,
                "distance": 0.1,
            },
        ]

        with patch.object(
            DocumentService, "search_chunks", new_callable=AsyncMock, return_value=mock_chunks
        ):
            result = await service._retrieve_document_context(uuid4(), "neural network")

        assert "invention.pdf" in result
        assert "neural network" in result

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_no_docs(self):
        mock_db = AsyncMock()
        service = DraftingService(mock_db)

        with patch.object(
            DocumentService, "search_chunks", new_callable=AsyncMock, return_value=[]
        ):
            result = await service._retrieve_document_context(uuid4(), "some query")

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_exception(self):
        mock_db = AsyncMock()
        service = DraftingService(mock_db)

        with patch.object(
            DocumentService, "search_chunks", new_callable=AsyncMock, side_effect=Exception("DB error")
        ):
            result = await service._retrieve_document_context(uuid4(), "some query")

        assert result == ""


# ---------------------------------------------------------------------------
# Integration test: generate_claims passes document_context to agent
# ---------------------------------------------------------------------------

class TestGenerateClaimsPassesDocumentContext:
    @pytest.mark.asyncio
    async def test_agent_receives_document_context(self):
        mock_db = AsyncMock()
        service = DraftingService(mock_db)

        # Mock _get_brief_text to return sample text
        service._get_brief_text = AsyncMock(return_value="Core Invention: A widget")

        # Mock _retrieve_document_context to return known context
        service._retrieve_document_context = AsyncMock(
            return_value="[doc.pdf, Page 1]: Technical detail about widget"
        )

        # Capture the state passed to the agent
        captured_state = {}

        async def mock_ainvoke(state):
            captured_state.update(state)
            return {
                "claim_graph": MagicMock(model_dump=MagicMock(return_value={"nodes": [], "risk_score": 50})),
                "errors": [],
            }

        with patch("src.drafting.service.claims_agent") as mock_agent:
            mock_agent.ainvoke = mock_ainvoke

            # Mock DB queries for version number and matter state
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.get = AsyncMock(return_value=None)
            mock_db.add = MagicMock()
            mock_db.flush = AsyncMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            await service.generate_claims(uuid4())

        assert "document_context" in captured_state
        assert "Technical detail about widget" in captured_state["document_context"]
