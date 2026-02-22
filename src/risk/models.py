from sqlalchemy import Column, String, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.database import Base
from src.shared.models import AuditMixin


class RiskAnalysisVersion(Base, AuditMixin):
    __tablename__ = "risk_analysis_versions"

    matter_id = Column(ForeignKey("matters.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    description = Column(String, nullable=True)
    is_authoritative = Column(Boolean, default=False)

    # The structured risk analysis
    analysis_data = Column(JSONB, nullable=False)

    # Track which claims were analyzed
    claim_version_id = Column(ForeignKey("claim_graph_versions.id"), nullable=True)

    matter = relationship("Matter", back_populates="risk_versions")
    claim_version = relationship("ClaimGraphVersion")
