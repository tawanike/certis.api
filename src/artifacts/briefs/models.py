from sqlalchemy import Column, String, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.database import Base
from src.shared.models import AuditMixin

class BriefVersion(Base, AuditMixin):
    __tablename__ = "brief_versions"
    
    matter_id = Column(ForeignKey("matters.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    source_material_hash = Column(String, nullable=True) # SHA-256 for change detection
    is_authoritative = Column(Boolean, default=False)
    
    # The structured output from Phase 1 (SBD)
    structure_data = Column(JSONB, nullable=False) 
    
    matter = relationship("Matter", back_populates="brief_versions")
