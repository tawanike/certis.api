from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
from src.database import Base
from src.shared.models import AuditMixin


class Client(Base, AuditMixin):
    """Patent applicant / client entity."""
    __tablename__ = "clients"

    name = Column(String, nullable=False)
    company = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    tenant_id = Column(ForeignKey("tenants.id"), nullable=False)

    tenant = relationship("src.auth.models.Tenant")
    matters = relationship("src.matter.models.Matter", back_populates="client")
