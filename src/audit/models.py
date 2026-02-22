from enum import Enum
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from src.database import Base
from src.shared.models import AuditMixin


class AuditEventType(str, Enum):
    BRIEF_UPLOADED = "BRIEF_UPLOADED"
    BRIEF_APPROVED = "BRIEF_APPROVED"
    CLAIMS_GENERATED = "CLAIMS_GENERATED"
    CLAIMS_COMMITTED = "CLAIMS_COMMITTED"
    RISK_ANALYZED = "RISK_ANALYZED"
    RISK_COMMITTED = "RISK_COMMITTED"
    SPEC_GENERATED = "SPEC_GENERATED"
    SPEC_COMMITTED = "SPEC_COMMITTED"
    RISK_RE_EVALUATED = "RISK_RE_EVALUATED"
    RISK_RE_EVAL_COMMITTED = "RISK_RE_EVAL_COMMITTED"
    QA_VALIDATED = "QA_VALIDATED"
    QA_COMMITTED = "QA_COMMITTED"
    MATTER_LOCKED = "MATTER_LOCKED"
    EXPORT_GENERATED = "EXPORT_GENERATED"


class AuditEvent(Base, AuditMixin):
    __tablename__ = "audit_events"

    matter_id = Column(ForeignKey("matters.id"), nullable=False, index=True)
    event_type = Column(SAEnum(AuditEventType), nullable=False)
    actor_id = Column(ForeignKey("users.id"), nullable=True)
    artifact_version_id = Column(UUID(as_uuid=True), nullable=True)
    artifact_type = Column(String, nullable=True)  # "brief" | "claims" | "risk" | "spec" | "qa"
    detail = Column(JSONB, nullable=True)

    matter = relationship("Matter", back_populates="audit_events")
    actor = relationship("src.auth.models.User")
