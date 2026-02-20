from sqlalchemy import Column, String, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.database import Base
from src.shared.models import AuditMixin

class ClaimGraphVersion(Base, AuditMixin):
    __tablename__ = "claim_graph_versions"
    
    matter_id = Column(ForeignKey("matters.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    description = Column(String, nullable=True)
    is_authoritative = Column(Boolean, default=False)
    
    # The structured claims
    graph_data = Column(JSONB, nullable=False)
    
    matter = relationship("Matter", back_populates="claim_versions")
