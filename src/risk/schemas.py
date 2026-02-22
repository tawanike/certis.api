from typing import List, Optional, Literal, Any, Dict
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RiskFinding(BaseModel):
    id: str = Field(..., description="Finding ID, e.g. 'R1', 'R2'")
    claim_id: str = Field(..., description="References ClaimNode.id that this finding applies to")
    category: Literal[
        "functional_claiming",
        "means_plus_function",
        "ambiguous_terms",
        "lack_of_structural_support",
        "section_101_eligibility",
        "indefiniteness",
        "written_description",
    ]
    severity: Literal["high", "medium", "low"]
    title: str = Field(..., description="Short label for the finding")
    description: str = Field(..., description="Detailed explanation of the vulnerability")
    recommendation: str = Field(..., description="Suggested fix or mitigation")


class RiskAnalysis(BaseModel):
    defensibility_score: int = Field(..., ge=0, le=100, description="Overall defensibility score")
    findings: List[RiskFinding] = Field(description="List of identified risk findings")
    summary: str = Field(..., description="Overall assessment of the claim set's litigation risk")


class RiskAnalysisVersionResponse(BaseModel):
    id: UUID
    matter_id: UUID
    version_number: int
    description: Optional[str]
    is_authoritative: bool
    created_at: datetime
    analysis_data: Dict[str, Any]
    claim_version_id: Optional[UUID]
    spec_version_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)
