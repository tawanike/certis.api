from typing import List, Optional, Literal, Any, Dict
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class ClaimNode(BaseModel):
    id: str = Field(..., description="Unique ID for the claim (e.g., '1', '2', '3')")
    type: Literal["independent", "dependent"]
    text: str = Field(..., description="The full text of the claim")
    dependencies: List[str] = Field(default=[], description="List of parent claim IDs this claim depends on")
    category: Optional[Literal["method", "system", "apparatus", "crm"]] = None

class ClaimGraph(BaseModel):
    nodes: List[ClaimNode] = Field(description="List of all claims in the set")
    risk_score: Optional[int] = Field(None, description="Overall risk score (0-100)")

class ClaimGraphVersionResponse(BaseModel):
    id: UUID
    matter_id: UUID
    version_number: int
    description: Optional[str]
    is_authoritative: bool
    created_at: datetime
    graph_data: Dict[str, Any] # or ClaimGraph if we want it parsed

    model_config = ConfigDict(from_attributes=True)
