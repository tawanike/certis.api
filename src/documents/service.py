import hashlib
import logging
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

    async def upload_and_process(
        self,
        matter_id: UUID,
        filename: str,
        file_content: bytes,
        content_type: str = "application/pdf",
    ) -> Document:
        """Upload a document, extract pages, embed chunks, store everything."""
        # 1. Hash for dedup
        file_hash = hashlib.sha256(file_content).hexdigest()

        # Check for duplicate
        existing = await self.db.execute(
            select(Document).where(
                Document.matter_id == matter_id,
                Document.file_hash == file_hash,
            )
        )
        if existing.scalars().first():
            raise ValueError(f"Document already uploaded (hash: {file_hash[:12]}...)")

        # 2. Create document record
        doc = Document(
            matter_id=matter_id,
            filename=filename,
            content_type=content_type,
            file_hash=file_hash,
            status=DocumentStatus.PROCESSING,
        )
        self.db.add(doc)
        await self.db.flush()

        try:
            # 3. Extract pages using PyPDFLoader via IngestionService
            pages = self.ingestion.extract_pages(file_content, filename)
            doc.total_pages = len(pages)
            doc.raw_text = "\n\n".join([p["content"] for p in pages])

            # 4. Chunk and embed each page
            all_chunks = []
            for page in pages:
                # Split long pages into sub-chunks
                sub_chunks = self.text_splitter.split_text(page["content"])
                for chunk_text in sub_chunks:
                    if chunk_text.strip():
                        all_chunks.append({
                            "page_number": page["page_number"],
                            "content": chunk_text,
                        })

            # 5. Generate embeddings in batch
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
    ) -> List[DocumentChunk]:
        """Vector similarity search across all document chunks for a matter."""
        # 1. Embed the query
        query_embedding = await self.embeddings.aembed_query(query)

        # 2. Cosine similarity search via pgvector
        result = await self.db.execute(
            text("""
                SELECT dc.id, dc.document_id, dc.page_number, dc.content, dc.token_count,
                       dc.embedding <=> :query_embedding AS distance, d.filename
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.matter_id = :matter_id
                  AND d.status = 'ready'
                  AND dc.embedding IS NOT NULL
                ORDER BY dc.embedding <=> :query_embedding
                LIMIT :top_k
            """),
            {
                "query_embedding": str(query_embedding),
                "matter_id": str(matter_id),
                "top_k": top_k,
            },
        )
        rows = result.fetchall()

        # Return as list of dicts with content and metadata
        return [
            {
                "id": str(row[0]),
                "document_id": str(row[1]),
                "page_number": row[2],
                "content": row[3],
                "token_count": row[4],
                "distance": row[5],
                "filename": row[6],
            }
            for row in rows
        ]

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
