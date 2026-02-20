from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.config import settings
from src.auth import security, models
from src.auth.service import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Eager load groups and permissions for RBAC
    query = select(models.User).where(models.User.email == email).options(
        selectinload(models.User.groups).selectinload(models.Group.permissions)
    )
    result = await db.execute(query)
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

class CheckPermission:
    def __init__(self, codename: str):
        self.codename = codename

    async def __call__(self, user: models.User = Depends(get_current_active_user)):
        # Super admin check (optional, if we have a superuser flag or group)
        # For now, iterate groups
        has_perm = False
        for group in user.groups:
            for permission in group.permissions:
                if permission.codename == self.codename:
                    has_perm = True
                    break
            if has_perm:
                break
        
        if not has_perm:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {self.codename}",
            )
        return True
