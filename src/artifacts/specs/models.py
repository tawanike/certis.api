from sqlalchemy import Column, String, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.database import Base
from src.shared.models import AuditMixin

class SpecVersion(Base, AuditMixin):
    __tablename__ = "spec_versions"

    matter_id = Column(ForeignKey("matters.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    description = Column(String, nullable=True)
    is_authoritative = Column(Boolean, default=False)

    # The generated text sections
    content_data = Column(JSONB, nullable=False)
    format_style = Column(String, default="USPTO_Standard")

    # Traceability: which claims and risk findings informed this spec
    claim_version_id = Column(ForeignKey("claim_graph_versions.id"), nullable=True)
    risk_version_id = Column(ForeignKey("risk_analysis_versions.id"), nullable=True)

    matter = relationship("Matter", back_populates="spec_versions")
    claim_version = relationship("ClaimGraphVersion")
    risk_version = relationship("RiskAnalysisVersion", foreign_keys=[risk_version_id])
