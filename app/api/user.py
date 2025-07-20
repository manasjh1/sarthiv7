from fastapi import APIRouter, Depends
from app.auth import get_current_user
from app.models import User
from app.schemas import UserProfileResponse
import logging

router = APIRouter(prefix="/api/user", tags=["user"])

@router.get("/me", response_model=UserProfileResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    logging.info(f"Getting info for user_id: {current_user.user_id}")
    return UserProfileResponse(
        user_id=str(current_user.user_id),
        name=current_user.name or "",
        email=current_user.email or "",
        phone_number=current_user.phone_number or 0,
        is_verified=getattr(current_user, 'is_verified', True),
        user_type=current_user.user_type,
        proficiency_score=current_user.proficiency_score,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
        updated_at=current_user.updated_at.isoformat() if current_user.updated_at else None
    )
