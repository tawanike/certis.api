from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_tenant_matter
from src.auth.models import User
from src.database import get_db
from src.audit.models import AuditEvent
from src.audit.schemas import AuditEventResponse

router = APIRouter(prefix="/matters", tags=["audit"])


@router.get("/{matter_id}/audit", response_model=List[AuditEventResponse])
async def list_audit_events(
    matter_id: UUID,
    current_user: User = Depends(require_tenant_matter),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.matter_id == matter_id)
        .order_by(desc(AuditEvent.created_at))
    )
    result = await db.execute(stmt)
    return result.scalars().all()
