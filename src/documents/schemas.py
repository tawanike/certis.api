from uuid import UUID
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    id: UUID
    matter_id: UUID
    filename: str
    content_type: str
    total_pages: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkResponse(BaseModel):
    id: UUID
    document_id: UUID
    page_number: int
    content: str
    token_count: int

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(DocumentResponse):
    chunks: List[DocumentChunkResponse] = []


class SearchResult(BaseModel):
    id: str
    document_id: str
    page_number: int
    content: str
    token_count: int
    distance: float
    filename: str = ""
    content_type: str = ""
    total_pages: int = 0
