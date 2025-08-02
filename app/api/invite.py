from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt, JWTError
from app.database import get_db
from app.models import InviteCode
from app.schemas import InviteValidateRequest, InviteValidateResponse
from app.config import settings
import logging

router = APIRouter(prefix="/api/invite", tags=["auth"])

def create_invite_token(invite_id: str, invite_code: str) -> str:
    """Create invite JWT token"""
    expire = datetime.utcnow() + timedelta(hours=1)
    to_encode = {
        "invite_id": invite_id,
        "invite_code": invite_code,
        "type": "invite",
        "exp": expire,
        "iat": datetime.utcnow()
    }
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

def verify_invite_token(token: str) -> dict:
    """Verify invite JWT token with improved error handling"""
    try:
        if not token or not isinstance(token, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Invalid token format"
            )
            
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        
        if payload.get("type") != "invite":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid token type"
            )
            
        invite_id = payload.get("invite_id")
        invite_code = payload.get("invite_code")
        
        if not invite_id or not invite_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid token payload"
            )
            
        return {
            "invite_id": invite_id,
            "invite_code": invite_code
        }
        
    except JWTError as e:
        logging.error(f"JWT Error in invite token verification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid or expired invite token"
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in invite token verification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Token verification failed"
        )

@router.post("/validate", response_model=InviteValidateResponse)
def validate_invite_code(
    request: InviteValidateRequest,
    db: Session = Depends(get_db)
):
    try:
        # Input validation
        if not request.invite_code or not isinstance(request.invite_code, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invite code is required"
            )
            
        invite_code = request.invite_code.strip().upper()
        
        if len(invite_code) < 3 or len(invite_code) > 64:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invite code format"
            )
            
        logging.info(f"Validating invite code: {invite_code}")

        # Database lookup with error handling
        try:
            existing_invite = db.query(InviteCode).filter(
                InviteCode.invite_code == invite_code
            ).first()
        except Exception as e:
            logging.error(f"Database error looking up invite code {invite_code}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred"
            )

        if not existing_invite:
            return InviteValidateResponse(
                valid=False,
                message=f"Invite code '{invite_code}' does not exist. Please check your code and try again."
            )

        if existing_invite.is_used and existing_invite.user_id:
            return InviteValidateResponse(
                valid=False,
                message=f"Invite code '{invite_code}' has already been used by another user."
            )

        # Generate JWT token
        try:
            invite_jwt = create_invite_token(str(existing_invite.invite_id), invite_code)
        except Exception as e:
            logging.error(f"Error creating invite token for {invite_code}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate invite token"
            )

        return InviteValidateResponse(
            valid=True,
            message=f"Invite code '{invite_code}' is valid!",
            invite_id=str(existing_invite.invite_id),
            invite_token=invite_jwt
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in validate_invite_code: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invite validation failed"
        )