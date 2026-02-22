from typing import List, Optional, Dict, Any, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class SpecParagraph(BaseModel):
    id: str = Field(..., description="Paragraph ID, e.g. 'P1', 'P2'")
    section: Literal[
        "technical_field",
        "background",
        "summary",
        "brief_description_of_drawings",
        "detailed_description",
        "definitions",
        "abstract",
    ]
    text: str = Field(..., description="Paragraph content")
    claim_references: List[str] = Field(
        default=[], description="ClaimNode IDs this paragraph supports"
    )


class SpecDocument(BaseModel):
    title: str = Field(..., description="Invention title for the specification")
    sections: List[SpecParagraph] = Field(description="All paragraphs in the specification")
    claim_coverage: Dict[str, List[str]] = Field(
        default={}, description="Mapping of claim_id to list of paragraph IDs that support it"
    )


class SpecVersionResponse(BaseModel):
    id: UUID
    matter_id: UUID
    version_number: int
    description: Optional[str]
    is_authoritative: bool
    created_at: datetime
    content_data: Dict[str, Any]
    claim_version_id: Optional[UUID]
    risk_version_id: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)
