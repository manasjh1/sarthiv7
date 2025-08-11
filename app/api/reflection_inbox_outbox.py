from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any
from app.database import get_db
from app.auth import get_current_user
from app.models import User, Reflection, CategoryDict
import logging

router = APIRouter(
    prefix="/api/reflection",
    tags=["reflection-inbox-outbox"]
)

@router.get("/inbox")
async def get_inbox(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """All reflections where current user is the receiver."""
    try:
        reflections = db.query(
            Reflection.reflection_id,
            Reflection.reflection,
            Reflection.name,
            Reflection.relation,
            Reflection.created_at,
            Reflection.stage_no,
            CategoryDict.category_name
        ).join(
            CategoryDict,
            Reflection.category_no == CategoryDict.category_no,
            isouter=True
        ).filter(
            Reflection.receiver_user_id == current_user.user_id,
            Reflection.status == 1
        ).order_by(
            Reflection.created_at.desc()
        ).all()

        reflection_list = []
        for r in reflections:
            summary_preview = (
                r.reflection[:50] + "..."
                if r.reflection and len(r.reflection) > 50
                else (r.reflection or "No summary available")
            )
            reflection_list.append({
                "reflection_id": str(r.reflection_id),
                "name": r.name or "Unknown",
                "relation": r.relation or "",
                "category": r.category_name or "General",
                "summary": summary_preview,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "stage": r.stage_no
            })

        return {
            "success": True,
            "message": "Inbox retrieved successfully",
            "data": {"reflections": reflection_list}
        }

    except Exception as e:
        logging.error(f"Error in get_inbox: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/outbox")
async def get_outbox(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """All reflections where current user is the giver (sender)."""
    try:
        reflections = db.query(
            Reflection.reflection_id,
            Reflection.reflection,
            Reflection.name,
            Reflection.relation,
            Reflection.created_at,
            Reflection.stage_no,
            CategoryDict.category_name
        ).join(
            CategoryDict,
            Reflection.category_no == CategoryDict.category_no,
            isouter=True
        ).filter(
            Reflection.giver_user_id == current_user.user_id,
            Reflection.status == 1
        ).order_by(
            Reflection.created_at.desc()
        ).all()

        reflection_list = []
        for r in reflections:
            summary_preview = (
                r.reflection[:50] + "..."
                if r.reflection and len(r.reflection) > 50
                else (r.reflection or "No summary available")
            )
            reflection_list.append({
                "reflection_id": str(r.reflection_id),
                "name": r.name or "Unknown",
                "relation": r.relation or "",
                "category": r.category_name or "General",
                "summary": summary_preview,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "stage": r.stage_no
            })

        return {
            "success": True,
            "message": "Outbox retrieved successfully",
            "data": {"reflections": reflection_list}
        }

    except Exception as e:
        logging.error(f"Error in get_outbox: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
