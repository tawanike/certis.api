from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict
from uuid import UUID

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    tenant_id: str  # For now, explicit tenant ID until we have tenant resolution

class UserRegister(BaseModel):
    invite_code: str
    password: str
    full_name: str

class InvitationCreate(BaseModel):
    email: EmailStr
    group_id: Optional[UUID] = None

class InvitationResponse(BaseModel):
    code: str
    email: str
    expires_at: datetime
    status: str
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)
