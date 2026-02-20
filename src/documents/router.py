import hashlib
from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import require_tenant_matter
from src.documents.service import DocumentService
from src.documents.models import Document, DocumentStatus
from src.documents.schemas import DocumentResponse, DocumentDetailResponse, SearchResult

router = APIRouter(prefix="/matters/{matter_id}/documents", tags=["documents"])


async def _process_document_background(document_id: UUID, file_content: bytes):
    """Background task: extract pages, chunk, embed."""
    from src.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            service = DocumentService(db)
            doc = await db.get(Document, document_id)
            if not doc:
                return

            await service.process_document(doc, file_content)
        except Exception:
            pass


@router.post("", response_model=DocumentResponse, status_code=202)
async def upload_document(
    matter_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_tenant_matter),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document and process it in the background."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Dedup check
    file_hash = hashlib.sha256(content).hexdigest()
    existing = await db.execute(
        select(Document).where(
            Document.matter_id == matter_id,
            Document.file_hash == file_hash,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail=f"Document already uploaded (hash: {file_hash[:12]}...)")

    # Create document record immediately so the client has an ID
    doc = Document(
        matter_id=matter_id,
        filename=file.filename,
        content_type=file.content_type or "application/pdf",
        file_hash=file_hash,
        status=DocumentStatus.PROCESSING,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Dispatch heavy processing to background
    background_tasks.add_task(_process_document_background, doc.id, content)

    return doc


@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    matter_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    """List all documents for a matter."""
    service = DocumentService(db)
    return await service.list_documents(matter_id)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    matter_id: UUID,
    document_id: UUID,
    current_user: User = Depends(require_tenant_matter),
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
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    """Search document chunks by semantic similarity."""
    service = DocumentService(db)
    return await service.search_chunks(matter_id, query, top_k)
