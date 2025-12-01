"""
JWT Authentication for the Bank Reconciliation API.
"""
from datetime import datetime, timedelta
from typing import Optional
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt

# Configuration
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", 60))

# Simple in-memory user store (replace with database in production)
USERS_DB = {
    "admin": {
        "username": "admin",
        "password_hash": "admin123",  # In production, use proper hashing (bcrypt)
        "role": "admin",
        "full_name": "Administrator"
    },
    "analyst": {
        "username": "analyst",
        "password_hash": "analyst123",
        "role": "analyst",
        "full_name": "Financial Analyst"
    },
    "viewer": {
        "username": "viewer",
        "password_hash": "viewer123",
        "role": "viewer",
        "full_name": "Read-Only User"
    }
}

# Role permissions
ROLE_PERMISSIONS = {
    "admin": ["read", "write", "delete", "admin"],
    "analyst": ["read", "write"],
    "viewer": ["read"]
}

security = HTTPBearer(auto_error=False)


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class TokenData(BaseModel):
    """Token payload data."""
    username: str
    role: str
    exp: datetime


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class User(BaseModel):
    """User model."""
    username: str
    role: str
    full_name: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash.
    In production, use bcrypt or argon2.
    """
    # Simple comparison for demo - use proper hashing in production!
    return plain_password == hashed_password


def get_user(username: str) -> Optional[dict]:
    """Get user from database."""
    return USERS_DB.get(username)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate user credentials."""
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        exp: datetime = datetime.fromtimestamp(payload.get("exp"))

        if username is None:
            return None

        return TokenData(username=username, role=role, exp=exp)
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[User]:
    """
    Get current user from JWT token.
    Returns None if no token or invalid token (for optional auth).
    """
    if not credentials:
        return None

    token_data = decode_token(credentials.credentials)
    if not token_data:
        return None

    user = get_user(token_data.username)
    if not user:
        return None

    return User(
        username=user["username"],
        role=user["role"],
        full_name=user["full_name"]
    )


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Require valid authentication.
    Raises 401 if not authenticated.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token_data = decode_token(credentials.credentials)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = get_user(token_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return User(
        username=user["username"],
        role=user["role"],
        full_name=user["full_name"]
    )


def require_permission(permission: str):
    """
    Dependency factory for permission checking.
    Usage: Depends(require_permission("write"))
    """
    async def permission_checker(user: User = Depends(require_auth)) -> User:
        user_permissions = ROLE_PERMISSIONS.get(user.role, [])
        if permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required"
            )
        return user

    return permission_checker


def require_admin(user: User = Depends(require_auth)) -> User:
    """Require admin role."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user
