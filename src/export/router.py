from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_tenant_matter
from src.auth.models import User
from src.database import get_db
from src.export.service import ExportService
from src.matter.schemas import MatterResponse

router = APIRouter(prefix="/matters", tags=["export"])


@router.post("/{matter_id}/lock", response_model=MatterResponse)
async def lock_matter_for_export(
    matter_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = ExportService(db)
    return await service.lock_for_export(matter_id, current_user.id)


@router.get("/{matter_id}/export/docx")
async def export_docx(
    matter_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    service = ExportService(db)
    docx_bytes = await service.generate_docx(matter_id, current_user.id)

    import io
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=patent_{matter_id}.docx"},
    )
