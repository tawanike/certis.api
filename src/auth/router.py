from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.auth import schemas, models, security
from src.auth.service import AuthService
from src.config import settings

from src.auth.dependencies import get_current_user, CheckPermission

router = APIRouter()

@router.get("/test-permission/write")
async def test_permission_write(user: models.User = Depends(CheckPermission("test:write"))):
    """Temporary test endpoint for RBAC verification."""
    return {"message": "You have testing write access"}

@router.post("/login", response_model=schemas.Token)
async def login_access_token(
    login_data: schemas.UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    JSON login endpoint — accepts {"email": "...", "password": "..."}
    """
    auth_service = AuthService(db)
    user = await auth_service.authenticate_user(login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password",
        )
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.email, "tenant_id": str(user.tenant_id)},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }

@router.post("/invitations", response_model=schemas.InvitationResponse)
async def create_invitation(
    invite_data: schemas.InvitationCreate,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create an invitation. Requires authentication.
    """
    auth_service = AuthService(db)
    try:
        invitation = await auth_service.create_invitation(
            inviter=current_user,
            email=invite_data.email,
            group_id=invite_data.group_id
        )
        return invitation
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/invitations/{code}", response_model=schemas.InvitationResponse)
async def validate_invitation(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate an invitation code. Public endpoint.
    """
    auth_service = AuthService(db)
    try:
        invitation = await auth_service.validate_invitation(code)
        return invitation
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/register", response_model=schemas.Token)
async def register(
    register_data: schemas.UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user with a valid invitation code.
    """
    auth_service = AuthService(db)
    try:
        user = await auth_service.register_with_invitation(register_data)
        
        # Log them in immediately
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = security.create_access_token(
            data={"sub": user.email, "tenant_id": str(user.tenant_id)},
            expires_delta=access_token_expires
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
