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
    mirror_source: Optional[str] = Field(None, description="ID of the system claim this was mirrored from")

class ClaimGraph(BaseModel):
    nodes: List[ClaimNode] = Field(description="List of all claims in the set")
    risk_score: Optional[int] = Field(None, description="Overall risk score (0-100)")
    canonical_model: Optional[Dict[str, Any]] = Field(None, description="Serialized CCM for audit")
    scope_validation: Optional[Dict[str, Any]] = Field(None, description="Serialized scope validation result")

class EditClaimRequest(BaseModel):
    text: Optional[str] = None
    type: Optional[Literal["independent", "dependent"]] = None
    category: Optional[Literal["method", "system", "apparatus", "crm"]] = None
    dependencies: Optional[List[str]] = None

class AddClaimRequest(BaseModel):
    type: Literal["independent", "dependent"]
    text: str
    category: Optional[Literal["method", "system", "apparatus", "crm"]] = None
    dependencies: List[str] = []

class ReorderClaimsRequest(BaseModel):
    node_ids: List[str]

class ClaimGraphVersionResponse(BaseModel):
    id: UUID
    matter_id: UUID
    version_number: int
    description: Optional[str]
    is_authoritative: bool
    created_at: datetime
    graph_data: Dict[str, Any] # or ClaimGraph if we want it parsed

    model_config = ConfigDict(from_attributes=True)
