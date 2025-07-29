from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import User
from app.schemas import OnboardingChoice
from app.auth import get_current_user

router = APIRouter(prefix="/api/user", tags=["user"])

# -------------------------
# Get current user profile
# -------------------------
@router.get("/me")
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return {
        "user_id": str(current_user.user_id),
        "email": current_user.email,
        "phone": current_user.phone,
        "name": current_user.name,
        "is_anonymous": current_user.is_anonymous,
    }

# -------------------------
# Save user onboarding choice
# -------------------------
@router.post("/onboarding")
async def set_onboarding_choice(
    data: OnboardingChoice,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if data.is_anonymous:
        current_user.name = None
        current_user.is_anonymous = True
    else:
        if not data.name:
            raise HTTPException(status_code=400, detail="Name is required for non-anonymous users.")
        current_user.name = data.name.strip()
        current_user.is_anonymous = False

    await db.commit()
    return {"message": "Onboarding information saved successfully."}
