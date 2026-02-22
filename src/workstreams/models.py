from enum import Enum
from sqlalchemy import Column, String, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from src.database import Base
from src.shared.models import AuditMixin

class WorkstreamTypeEnum(str, Enum):
    DRAFTING_APPLICATION = "DRAFTING_APPLICATION"
    OFFICE_ACTION_RESPONSE = "OFFICE_ACTION_RESPONSE"
    IDR_REVIEW = "IDR_REVIEW"

class WorkstreamStatusEnum(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    COMPLETED = "COMPLETED"

class Workstream(Base, AuditMixin):
    __tablename__ = "workstreams"
    
    matter_id = Column(ForeignKey("matters.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    
    workstream_type = Column(SAEnum(WorkstreamTypeEnum), nullable=False)
    status = Column(SAEnum(WorkstreamStatusEnum), default=WorkstreamStatusEnum.IN_PROGRESS, nullable=False)
    
    # The "Head" Pointers - These mutate as the user iterates
    active_brief_version_id = Column(ForeignKey("brief_versions.id"), nullable=True)
    active_claim_version_id = Column(ForeignKey("claim_graph_versions.id"), nullable=True)
    active_spec_version_id = Column(ForeignKey("spec_versions.id"), nullable=True)
    active_risk_version_id = Column(ForeignKey("risk_analysis_versions.id"), nullable=True)
    active_qa_version_id = Column(ForeignKey("qa_report_versions.id"), nullable=True)

    # Relationships
    matter = relationship("Matter", back_populates="workstreams")

    active_brief = relationship("BriefVersion", foreign_keys=[active_brief_version_id])
    active_claims = relationship("ClaimGraphVersion", foreign_keys=[active_claim_version_id])
    active_spec = relationship("SpecVersion", foreign_keys=[active_spec_version_id])
    active_risk = relationship("RiskAnalysisVersion", foreign_keys=[active_risk_version_id])
    active_qa = relationship("QAReportVersion", foreign_keys=[active_qa_version_id])
