from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.config import settings
from app.models import User
from app.database import get_db
import uuid
import logging

security = HTTPBearer()

def create_access_token(user_id: str, invite_id: str = None) -> str:
    """Create JWT access token for user with optional invite_id"""
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.utcnow()
    }
     
    # Add invite_id for new users
    if invite_id:
        to_encode["invite_id"] = invite_id
    
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> uuid.UUID:
    """Verify JWT token and return user ID"""
    try:
        payload = jwt.decode(
            credentials.credentials, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid token: missing user ID"
            )
        return uuid.UUID(user_id)
    except JWTError as e:
        logging.error(f"JWT Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid or expired token"
        )
    except ValueError as e:
        logging.error(f"Invalid user ID format: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid user ID format"
        )

def get_current_user(
    user_id: uuid.UUID = Depends(verify_token),
    db: Session = Depends(get_db)
) -> User:
    """Get current user from database"""
    try:
        user = db.query(User).filter(User.user_id == user_id, User.status == 1).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting current user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )