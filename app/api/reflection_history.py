from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
import uuid
import logging

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Reflection, Message, CategoryDict

# Create routeraw
router = APIRouter(
    prefix="/api/reflection",
    tags=["reflection-history"]
)


@router.post("/history")
async def get_reflection_history(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get reflection history for the current user
    
    Request formats:
    1. List all reflections: {"data": {"mode": "get_reflections"}}
    2. Get specific reflection: {"data": {"mode": "get_reflections", "reflection_id": "uuid"}}
    """
    try:
        # Extract request data
        data = request.get("data", {})
        mode = data.get("mode")
        reflection_id = data.get("reflection_id")
        
        if mode != "get_reflections":
            raise HTTPException(status_code=400, detail="Invalid mode. Use 'get_reflections'")
        
        # Case 1: Get all reflections
        if not reflection_id:
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
            
            # Format response
            reflection_list = []
            for r in reflections:
                # Create summary preview
                if r.reflection:
                    summary_preview = r.reflection[:50] + "..." if len(r.reflection) > 50 else r.reflection
                elif r.stage_no < 4:
                    summary_preview = f"In progress (Stage {r.stage_no})"
                else:
                    summary_preview = "No summary available"
                
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
                "message": "Reflections retrieved successfully",
                "data": {"reflections": reflection_list}
            }
        
        # Case 2: Get specific reflection details
        else:
            try:
                reflection_uuid = uuid.UUID(reflection_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid reflection_id format")
            
            # Get reflection
            reflection = db.query(
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
                Reflection.reflection_id == reflection_uuid,
                Reflection.giver_user_id == current_user.user_id,
                Reflection.status == 1
            ).first()
            
            if not reflection:
                raise HTTPException(status_code=404, detail="Reflection not found")
            
            
            messages = db.query(Message).filter(
                Message.reflection_id == reflection_uuid,
                Message.status == 1,
                Message.stage_no == 4   
            ).order_by(Message.created_at).all()
            
            # Format messages
            message_list = [{
                "sender": "user" if msg.sender == 1 else "assistant",
                "content": msg.text,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None,
                "stage": msg.stage_no,
                "is_distress": msg.is_distress
            } for msg in messages]
            
            return {
                "success": True,
                "message": "Reflection detail fetched",
                "data": {
                    "reflection_id": str(reflection.reflection_id),
                    "name": reflection.name or "Unknown",
                    "relation": reflection.relation or "",
                    "category": reflection.category_name or "General",
                    "summary": reflection.reflection or "No summary available",
                    "created_at": reflection.created_at.isoformat() if reflection.created_at else None,
                    "stage": reflection.stage_no,
                    "messages": message_list
                }
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in get_reflection_history: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")