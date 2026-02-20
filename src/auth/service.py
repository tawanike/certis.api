from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from src.auth import models, schemas, security

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> Optional[models.User]:
        result = await self.db.execute(select(models.User).where(models.User.email == email))
        return result.scalars().first()

    async def authenticate_user(self, email: str, password: str) -> Optional[models.User]:
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not security.verify_password(password, user.hashed_password):
            return None
        return user

    async def create_user(self, user_create: schemas.UserCreate) -> models.User:
        hashed_password = security.get_password_hash(user_create.password)
        db_user = models.User(
            email=user_create.email,
            hashed_password=hashed_password,
            full_name=user_create.full_name,
            tenant_id=user_create.tenant_id,  # TODO: Tenant logic
        )
        self.db.add(db_user)
        await self.db.commit()
        await self.db.refresh(db_user)
        return db_user

    async def create_invitation(self, inviter: models.User, email: str, group_id: Optional[UUID] = None) -> models.Invitation:
        # Check if user already exists
        existing_user = await self.get_user_by_email(email)
        if existing_user:
            raise ValueError("User with this email already exists")

        # Generate secure code
        code = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)

        invitation = models.Invitation(
            code=code,
            email=email,
            tenant_id=inviter.tenant_id,
            group_id=group_id,
            inviter_id=inviter.id,
            expires_at=expires_at,
            status="PENDING"
        )
        self.db.add(invitation)
        await self.db.commit()
        await self.db.refresh(invitation)
        return invitation

    async def validate_invitation(self, code: str) -> models.Invitation:
        result = await self.db.execute(select(models.Invitation).where(models.Invitation.code == code))
        invitation = result.scalars().first()
        
        if not invitation:
            raise ValueError("Invalid invitation code")
        
        if invitation.status != "PENDING":
            raise ValueError("Invitation is no longer valid")
            
        if invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            invitation.status = "EXPIRED"
            await self.db.commit()
            raise ValueError("Invitation has expired")
            
        return invitation

    async def register_with_invitation(self, register_data: schemas.UserRegister) -> models.User:
        # validate invite again
        invitation = await self.validate_invitation(register_data.invite_code)
        
        # create user
        hashed_password = security.get_password_hash(register_data.password)
        user = models.User(
            email=invitation.email,
            hashed_password=hashed_password,
            full_name=register_data.full_name,
            tenant_id=invitation.tenant_id
        )
        
        # Add to group if specified
        if invitation.group_id:
            # Logic to add to group would go here (need to handle many-to-many)
            # For now, just create user.
            pass

        self.db.add(user)
        
        # update invitation
        invitation.status = "ACCEPTED"
        
        await self.db.commit()
        await self.db.refresh(user)
        return user
