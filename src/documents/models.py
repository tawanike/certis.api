from enum import Enum
from sqlalchemy import Column, String, Integer, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from src.database import Base
from src.shared.models import AuditMixin


class DocumentStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base, AuditMixin):
    """Uploaded document (PDF, DOCX, etc.) linked to a matter."""
    __tablename__ = "documents"

    matter_id = Column(ForeignKey("matters.id"), nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False, default="application/pdf")
    file_hash = Column(String(64), nullable=False)  # SHA-256
    total_pages = Column(Integer, default=0)
    raw_text = Column(Text, nullable=True)  # full extracted text
    status = Column(SAEnum(DocumentStatus), default=DocumentStatus.PROCESSING, nullable=False)

    matter = relationship("src.matter.models.Matter", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan",
                          order_by="DocumentChunk.page_number")


class DocumentChunk(Base, AuditMixin):
    """Page-level chunk with vector embedding for RAG retrieval."""
    __tablename__ = "document_chunks"

    document_id = Column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=True)  # pgvector
    token_count = Column(Integer, default=0)

    document = relationship("Document", back_populates="chunks")
