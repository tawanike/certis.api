from sqlalchemy import Column, String, ForeignKey, Boolean, Table, Integer, DateTime
from sqlalchemy.orm import relationship
from src.database import Base
from src.shared.models import AuditMixin

# Association Tables
group_permissions = Table(
    "group_permissions",
    Base.metadata,
    Column("group_id", ForeignKey("groups.id"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id"), primary_key=True),
)

user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("group_id", ForeignKey("groups.id"), primary_key=True),
)

class Permission(Base, AuditMixin):
    __tablename__ = "permissions"

    codename = Column(String, unique=True, nullable=False, index=True) # e.g. "matter:create"
    description = Column(String, nullable=True)

class Tenant(Base, AuditMixin):
    __tablename__ = "tenants"
    
    name = Column(String, nullable=False)
    domain = Column(String, unique=True, nullable=True)
    
    users = relationship("User", back_populates="tenant")
    groups = relationship("Group", back_populates="tenant")
    # Forward ref for Matter
    matters = relationship("src.matter.models.Matter", back_populates="tenant")

class Group(Base, AuditMixin):
    __tablename__ = "groups"

    name = Column(String, nullable=False)
    tenant_id = Column(ForeignKey("tenants.id"), nullable=False)

    tenant = relationship("Tenant", back_populates="groups")
    permissions = relationship("Permission", secondary=group_permissions)
    users = relationship("User", secondary=user_groups, back_populates="groups")

class User(Base, AuditMixin):
    __tablename__ = "users"
    
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    tenant_id = Column(ForeignKey("tenants.id"), nullable=False)
    
    tenant = relationship("Tenant", back_populates="users")
    groups = relationship("Group", secondary=user_groups, back_populates="users")
    
    # Forward reference to avoid circular imports, using string based relationship
    matters = relationship("src.matter.models.Matter", back_populates="attorney")

class Invitation(Base, AuditMixin):
    __tablename__ = "invitations"

    # id is inherited from AuditMixin or Base? Let's check shared/models.py first.
    # Assuming AuditMixin has id, created_at, updated_at.
    
    code = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, index=True, nullable=False)
    tenant_id = Column(ForeignKey("tenants.id"), nullable=False)
    group_id = Column(ForeignKey("groups.id"), nullable=True) # Role to assign
    inviter_id = Column(ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String, default="PENDING", nullable=False) # PENDING, ACCEPTED, EXPIRED

    tenant = relationship("Tenant")
    group = relationship("Group")
    inviter = relationship("User")
