from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship

from src.database import Base
from src.shared.models import AuditMixin


class TenantLLMConfig(Base, AuditMixin):
    __tablename__ = "tenant_llm_configs"

    tenant_id = Column(ForeignKey("tenants.id"), nullable=False, unique=True, index=True)

    # Per-role provider overrides (nullable = use env default)
    provider_primary = Column(String, nullable=True)
    provider_secondary = Column(String, nullable=True)
    provider_chat = Column(String, nullable=True)
    provider_vision = Column(String, nullable=True)
    provider_suggestions = Column(String, nullable=True)
    provider_embedding = Column(String, nullable=True)

    # Per-role model name overrides
    model_primary = Column(String, nullable=True)
    model_secondary = Column(String, nullable=True)
    model_chat = Column(String, nullable=True)
    model_vision = Column(String, nullable=True)
    model_suggestions = Column(String, nullable=True)
    model_embedding = Column(String, nullable=True)

    # Tenant-specific API keys
    openai_api_key = Column(String, nullable=True)
    azure_openai_api_key = Column(String, nullable=True)
    azure_openai_endpoint = Column(String, nullable=True)
    anthropic_api_key = Column(String, nullable=True)
    azure_foundry_api_key = Column(String, nullable=True)
    azure_foundry_endpoint = Column(String, nullable=True)

    tenant = relationship("src.auth.models.Tenant")
