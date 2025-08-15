from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import InviteCode
from app.schemas import InviteGenerateResponse
import random
import string
import logging

router = APIRouter(prefix="/api/invite", tags=["invite"])

def generate_invite_code() -> str:
    """Generate a random 8-character invite code"""
    characters = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return ''.join(random.choices(characters, k=8))

def is_invite_code_unique(invite_code: str, db: Session) -> bool:
    """Check if the generated invite code is unique"""
    existing = db.query(InviteCode).filter(
        InviteCode.invite_code == invite_code
    ).first()
    return existing is None

@router.post("/generate", response_model=InviteGenerateResponse)
def generate_new_invite_code(db: Session = Depends(get_db)):
    """
    Generate a new invite code
    
    Returns:
    - invite_code: The generated invite code
    - invite_id: The UUID of the invite record
    - created_at: When the invite was created
    """
    try:
        invite_code = None
        attempts = 0
        max_attempts = 10
        
        while attempts < max_attempts:
            candidate_code = generate_invite_code()
            if is_invite_code_unique(candidate_code, db):
                invite_code = candidate_code
                break
            attempts += 1
        
        if not invite_code:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate unique invite code after multiple attempts"
            )
        
        new_invite = InviteCode(
            invite_code=invite_code,
            is_used=False,
        )
        
        db.add(new_invite)
        db.commit()
        db.refresh(new_invite)
        
        logging.info(f"Generated new invite code: {invite_code} with ID: {new_invite.invite_id}")
        
        return InviteGenerateResponse(
            success=True,
            message="Invite code generated successfully",
            invite_code=invite_code,
            invite_id=str(new_invite.invite_id),
            created_at=new_invite.created_at.isoformat() if new_invite.created_at else None,
            is_used=False
        )
        
    except Exception as e:
        db.rollback()
        logging.error(f"Error generating invite code: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate invite code"
        )