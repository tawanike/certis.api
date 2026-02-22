from enum import Enum
from sqlalchemy import Column, String, ForeignKey, Enum as SAEnum, Table, ARRAY, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from src.database import Base
from src.shared.models import AuditMixin

class JurisdictionEnum(str, Enum):
    USPTO = "USPTO"
    EPO = "EPO"
    WIPO = "WIPO"
    JPO = "JPO"
    KIPO = "KIPO"
    CNIPA = "CNIPA"

class MatterTypeEnum(str, Enum):
    UTILITY = "UTILITY"
    DESIGN = "DESIGN"
    PLANT = "PLANT"
    PROVISIONAL = "PROVISIONAL"

# Association table for multi-jurisdiction support
matter_jurisdictions = Table(
    "matter_jurisdictions",
    Base.metadata,
    Column("matter_id", UUID(as_uuid=True), ForeignKey("matters.id"), primary_key=True),
    Column("jurisdiction", SAEnum(JurisdictionEnum), primary_key=True),
)

class MatterState(str, Enum):
    CREATED = "CREATED"
    BRIEF_ANALYZED = "BRIEF_ANALYZED"
    CLAIMS_PROPOSED = "CLAIMS_PROPOSED"
    CLAIMS_APPROVED = "CLAIMS_APPROVED"
    RISK_REVIEWED = "RISK_REVIEWED"
    SPEC_GENERATED = "SPEC_GENERATED"
    QA_COMPLETE = "QA_COMPLETE"
    LOCKED_FOR_EXPORT = "LOCKED_FOR_EXPORT"

class Matter(Base, AuditMixin):
    __tablename__ = "matters"
    
    title = Column(String, nullable=False)
    reference_number = Column(String, nullable=True)
    description = Column(String, nullable=True)
    inventors = Column(ARRAY(String), nullable=True)
    assignee = Column(String, nullable=True)
    tech_domain = Column(String, nullable=True)
    defensibility_score = Column(Integer, nullable=True)
    
    matter_type = Column(SAEnum(MatterTypeEnum), default=MatterTypeEnum.UTILITY, nullable=False)
    status = Column(SAEnum(MatterState), default=MatterState.CREATED, nullable=False)
    
    tenant_id = Column(ForeignKey("tenants.id"), nullable=False)
    attorney_id = Column(ForeignKey("users.id"), nullable=False)
    client_id = Column(PGUUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    
    tenant = relationship("src.auth.models.Tenant", back_populates="matters")
    attorney = relationship("src.auth.models.User", back_populates="matters")
    client = relationship("src.clients.models.Client", back_populates="matters")
    
    # Relationships to drafting artifacts
    brief_versions = relationship("BriefVersion", back_populates="matter", cascade="all, delete-orphan")
    claim_versions = relationship("ClaimGraphVersion", back_populates="matter", cascade="all, delete-orphan")
    spec_versions = relationship("SpecVersion", back_populates="matter", cascade="all, delete-orphan")
    risk_versions = relationship("RiskAnalysisVersion", back_populates="matter", cascade="all, delete-orphan")

    workstreams = relationship("Workstream", back_populates="matter", cascade="all, delete-orphan")
    documents = relationship("src.documents.models.Document", back_populates="matter", cascade="all, delete-orphan")
