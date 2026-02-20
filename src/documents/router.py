from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.documents.service import DocumentService
from src.documents.schemas import DocumentResponse, DocumentDetailResponse, SearchResult

router = APIRouter(prefix="/matters/{matter_id}/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse)
async def upload_document(
    matter_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload and process a document (extract pages, chunk, embed)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    service = DocumentService(db)
    try:
        doc = await service.upload_and_process(
            matter_id=matter_id,
            filename=file.filename,
            file_content=content,
            content_type=file.content_type or "application/pdf",
        )
        return doc
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    matter_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all documents for a matter."""
    service = DocumentService(db)
    return await service.list_documents(matter_id)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    matter_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get document details including chunk info."""
    service = DocumentService(db)
    doc = await service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/search", response_model=List[SearchResult])
async def search_documents(
    matter_id: UUID,
    query: str,
    top_k: int = 5,
    db: AsyncSession = Depends(get_db),
):
    """Search document chunks by semantic similarity."""
    service = DocumentService(db)
    return await service.search_chunks(matter_id, query, top_k)
