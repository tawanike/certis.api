from datetime import datetime
from uuid import UUID
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from src.matter.models import MatterState, JurisdictionEnum

class MatterBase(BaseModel):
    title: str
    reference_number: Optional[str] = None
    description: Optional[str] = None
    inventors: Optional[List[str]] = []
    assignee: Optional[str] = None
    tech_domain: Optional[str] = None
    defensibility_score: Optional[int] = None

class MatterCreate(MatterBase):
    jurisdictions: List[JurisdictionEnum] = [JurisdictionEnum.USPTO]

class MatterUpdate(MatterBase):
    title: Optional[str] = None
    status: Optional[MatterState] = None
    jurisdictions: Optional[List[JurisdictionEnum]] = None

class MatterResponse(MatterBase):
    id: UUID
    status: MatterState
    jurisdictions: List[str] = []
    tenant_id: UUID
    attorney_id: UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
