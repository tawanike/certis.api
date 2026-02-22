from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.audit.models import AuditEventType


class AuditEventResponse(BaseModel):
    id: UUID
    matter_id: UUID
    event_type: AuditEventType
    actor_id: Optional[UUID] = None
    artifact_version_id: Optional[UUID] = None
    artifact_type: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
