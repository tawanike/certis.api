import hashlib
import logging
from collections import defaultdict
from uuid import UUID
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.documents.models import Document, DocumentChunk, DocumentStatus
from src.ingestion.service import IngestionService
from src.llm.factory import get_embeddings

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.embeddings = get_embeddings()
        self.ingestion = IngestionService()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=200,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    async def process_document(self, doc: Document, file_content: bytes) -> Document:
        """Extract pages, chunk, embed, and store for an existing Document record.

        Called from a background task after the Document row has been created
        with status=PROCESSING.
        """
        try:
            # 1. Extract pages
            pages = self.ingestion.extract_pages(file_content, doc.filename)
            doc.total_pages = len(pages)
            doc.raw_text = "\n\n".join([p["content"] for p in pages])

            # 2. Chunk each page
            all_chunks = []
            for page in pages:
                sub_chunks = self.text_splitter.split_text(page["content"])
                for chunk_text in sub_chunks:
                    if chunk_text.strip():
                        all_chunks.append({
                            "page_number": page["page_number"],
                            "content": chunk_text,
                        })

            # 3. Generate embeddings in batch
            if all_chunks:
                texts = [c["content"] for c in all_chunks]
                embeddings = await self.embeddings.aembed_documents(texts)

                for chunk_data, embedding in zip(all_chunks, embeddings):
                    chunk = DocumentChunk(
                        document_id=doc.id,
                        page_number=chunk_data["page_number"],
                        content=chunk_data["content"],
                        embedding=embedding,
                        token_count=len(chunk_data["content"].split()),
                    )
                    self.db.add(chunk)

            doc.status = DocumentStatus.READY
            await self.db.commit()
            await self.db.refresh(doc)
            logger.info(f"Document {doc.id} processed: {len(pages)} pages, {len(all_chunks)} chunks")
            return doc

        except Exception as e:
            doc.status = DocumentStatus.FAILED
            await self.db.commit()
            logger.error(f"Document processing failed for {doc.id}: {e}")
            raise

    async def search_chunks(
        self,
        matter_id: UUID,
        query: str,
        top_k: int = 5,
        page_filter: Optional[int] = None,
    ) -> List[dict]:
        """Hybrid search: semantic + full-text with RRF reranking."""
        fetch_k = top_k * 2

        # 1. Semantic search via pgvector
        query_embedding = await self.embeddings.aembed_query(query)
        # Format as pgvector-compatible string: [0.1,0.2,...] with no spaces
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        semantic_result = await self.db.execute(
            text("""
                SELECT dc.id, dc.document_id, dc.page_number, dc.content, dc.token_count,
                       dc.embedding <=> cast(:query_embedding as vector) AS distance,
                       d.filename, d.content_type, d.total_pages
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.matter_id = :matter_id
                  AND d.status = 'READY'
                  AND dc.embedding IS NOT NULL
                ORDER BY dc.embedding <=> cast(:query_embedding as vector)
                LIMIT :fetch_k
            """),
            {
                "query_embedding": embedding_str,
                "matter_id": str(matter_id),
                "fetch_k": fetch_k,
            },
        )
        semantic_rows = semantic_result.fetchall()

        # 2. Full-text search via tsvector
        fts_result = await self.db.execute(
            text("""
                SELECT dc.id, dc.document_id, dc.page_number, dc.content, dc.token_count,
                       ts_rank(dc.search_vector, plainto_tsquery('english', :query)) AS fts_rank,
                       d.filename, d.content_type, d.total_pages
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.matter_id = :matter_id
                  AND d.status = 'READY'
                  AND dc.search_vector @@ plainto_tsquery('english', :query)
                ORDER BY fts_rank DESC
                LIMIT :fetch_k
            """),
            {
                "query": query,
                "matter_id": str(matter_id),
                "fetch_k": fetch_k,
            },
        )
        fts_rows = fts_result.fetchall()

        # 3. Merge with Reciprocal Rank Fusion
        merged = self._rrf_merge(semantic_rows, fts_rows, top_k=top_k, page_filter=page_filter)

        # 4. Return as list of dicts
        return [
            {
                "id": str(row[0]),
                "document_id": str(row[1]),
                "page_number": row[2],
                "content": row[3],
                "token_count": row[4],
                "distance": row[5],
                "filename": row[6],
                "content_type": row[7],
                "total_pages": row[8],
            }
            for row in merged
        ]

    @staticmethod
    def _rrf_merge(semantic_rows, fts_rows, k=60, top_k=5, page_filter=None):
        """Reciprocal Rank Fusion to merge semantic and full-text results."""
        scores = defaultdict(float)
        metadata = {}

        for rank, row in enumerate(semantic_rows):
            chunk_id = str(row[0])
            scores[chunk_id] += 1.0 / (k + rank + 1)
            metadata[chunk_id] = row

        for rank, row in enumerate(fts_rows):
            chunk_id = str(row[0])
            scores[chunk_id] += 1.0 / (k + rank + 1)
            if chunk_id not in metadata:
                metadata[chunk_id] = row

        # Page boost: if page_filter specified, boost matching chunks
        if page_filter is not None:
            for chunk_id, row in metadata.items():
                if row[2] == page_filter:  # page_number is index 2
                    scores[chunk_id] *= 2.0

        # Sort by RRF score descending, return top_k
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [metadata[chunk_id] for chunk_id, _ in ranked]

    @staticmethod
    def format_chunks_as_context(chunks: List[dict]) -> str:
        """Format search result chunks into a context string for agent prompts."""
        if not chunks:
            return ""
        parts = []
        for chunk in chunks:
            filename = chunk.get("filename", "unknown")
            page = chunk.get("page_number", "?")
            content = chunk.get("content", "")
            parts.append(f"[{filename}, Page {page}]: {content}")
        return "\n\n---\n\n".join(parts)

    async def list_documents(self, matter_id: UUID) -> List[Document]:
        """List all documents for a matter."""
        result = await self.db.execute(
            select(Document)
            .where(Document.matter_id == matter_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_document(self, document_id: UUID) -> Optional[Document]:
        """Get a single document with its chunks."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalars().first()
