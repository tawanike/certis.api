from sqlalchemy import Column, String, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.database import Base
from src.shared.models import AuditMixin

class SpecVersion(Base, AuditMixin):
    __tablename__ = "spec_versions"
    
    matter_id = Column(ForeignKey("matters.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    
    # The generated text sections
    content_data = Column(JSONB, nullable=False)
    format_style = Column(String, default="USPTO_Standard")
    
    matter = relationship("Matter", back_populates="spec_versions")
