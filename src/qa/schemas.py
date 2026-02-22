from typing import List, Optional, Literal, Any, Dict
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class QAFinding(BaseModel):
    id: str = Field(..., description="Finding ID, e.g. 'QA1', 'QA2'")
    category: Literal[
        "antecedent_basis",
        "dependency_loop",
        "undefined_term",
        "claim_spec_consistency",
        "support_coverage",
    ]
    severity: Literal["error", "warning"]
    claim_id: Optional[str] = Field(None, description="References ClaimNode.id if applicable")
    location: str = Field(..., description="Where the issue was found, e.g. 'Claim 1, Element 3'")
    title: str = Field(..., description="Short label for the finding")
    description: str = Field(..., description="Detailed explanation of the issue")
    recommendation: str = Field(..., description="Suggested fix")


class QAReport(BaseModel):
    support_coverage_score: int = Field(..., ge=0, le=100, description="Claim-to-spec support coverage percentage")
    total_errors: int = Field(..., description="Count of blocking errors")
    total_warnings: int = Field(..., description="Count of non-blocking warnings")
    findings: List[QAFinding] = Field(description="List of QA findings")
    summary: str = Field(..., description="Overall QA assessment")
    can_export: bool = Field(..., description="True only if total_errors == 0")


class QAReportVersionResponse(BaseModel):
    id: UUID
    matter_id: UUID
    version_number: int
    description: Optional[str]
    is_authoritative: bool
    created_at: datetime
    report_data: Dict[str, Any]
    claim_version_id: Optional[UUID]
    spec_version_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)
