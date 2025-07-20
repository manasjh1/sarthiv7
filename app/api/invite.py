from fastapi import APIRouter, Depends, HTTPException
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
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "invite":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return {
            "invite_id": payload.get("invite_id"),
            "invite_code": payload.get("invite_code")
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired invite token")

@router.post("/validate", response_model=InviteValidateResponse)
def validate_invite_code(
    request: InviteValidateRequest,
    db: Session = Depends(get_db)
):
    invite_code = request.invite_code.strip().upper()
    logging.info(f"Validating invite code: {invite_code}")

    existing_invite = db.query(InviteCode).filter(
        InviteCode.invite_code == invite_code
    ).first()

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

    invite_jwt = create_invite_token(str(existing_invite.invite_id), invite_code)

    return InviteValidateResponse(
        valid=True,
        message=f"Invite code '{invite_code}' is valid!",
        invite_id=str(existing_invite.invite_id),
        invite_token=invite_jwt
    )
