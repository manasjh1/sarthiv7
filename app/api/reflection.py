from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas import UniversalRequest, UniversalResponse
from app.auth import verify_token
from app.stage_handler import StageHandler
from app.database import get_db
import uuid

router = APIRouter(prefix="/api", tags=["reflection"])

@router.post("/reflection", response_model=UniversalResponse)
def process_reflection(
    request: UniversalRequest,
    user_id: uuid.UUID = Depends(verify_token),
    db: Session = Depends(get_db)
):
    try:
        handler = StageHandler(db)
        return handler.process_request(request, user_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
