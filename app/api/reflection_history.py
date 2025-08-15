from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Dict, Any
import uuid
import logging

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Reflection, Message, CategoryDict

# Create router
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
    
    - SENDERS: See full details (summary + messages + conversation history)
    - RECEIVERS: See ONLY the summary (no conversation history)
    
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
            return {
                "success": False,
                "message": "Invalid mode. Use 'get_reflections'",
                "data": {}
            }
        
        # Case 1: Get all reflections
        if not reflection_id:
            reflections = db.query(
                Reflection.reflection_id,
                Reflection.reflection,
                Reflection.name,
                Reflection.relation,
                Reflection.created_at,
                Reflection.stage_no,
                Reflection.giver_user_id,
                Reflection.receiver_user_id,
                Reflection.sender_name,
                Reflection.is_anonymous,  # Added this field
                CategoryDict.category_name
            ).join(
                CategoryDict, 
                Reflection.category_no == CategoryDict.category_no,
                isouter=True
            ).filter(
                # User can be EITHER giver OR receiver
                or_(
                    Reflection.giver_user_id == current_user.user_id,
                    Reflection.receiver_user_id == current_user.user_id
                ),
                Reflection.status == 1
            ).order_by(
                Reflection.created_at.desc()
            ).all()
            
            # Format response
            reflection_list = []
            for r in reflections:
                # Determine if user is sender or receiver
                is_sender = (r.giver_user_id == current_user.user_id)
                user_role = "sent" if is_sender else "received"
                
                # Create summary preview - same for both sender and receiver
                if r.reflection:
                    summary_preview = r.reflection[:50] + "..." if len(r.reflection) > 50 else r.reflection
                elif r.stage_no < 4:
                    summary_preview = f"In progress (Stage {r.stage_no})" if is_sender else "Reflection in progress"
                else:
                    summary_preview = "No summary available"
                
                # Determine display name based on anonymity choice
                if r.is_anonymous is False and r.sender_name:
                    display_name = r.sender_name
                elif r.is_anonymous is False and r.name:
                    display_name = r.name  # Fallback to reflection.name
                else:
                    display_name = "Anonymous"
                
                reflection_list.append({
                    "reflection_id": str(r.reflection_id),
                    "name": r.name or "Unknown",
                    "relation": r.relation or "",
                    "category": r.category_name or "General",
                    "summary": summary_preview,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "stage": r.stage_no,
                    "user_role": user_role,
                    "is_sender": is_sender,
                    "sender_name": r.sender_name,
                    "is_anonymous": r.is_anonymous,
                    "display_name": display_name  # This is what frontend should show for "from"
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
                return {
                    "success": False,
                    "message": "Invalid reflection_id format",
                    "data": {}
                }
            
            # Get reflection
            reflection = db.query(
                Reflection.reflection_id,
                Reflection.reflection,
                Reflection.name,
                Reflection.relation,
                Reflection.created_at,
                Reflection.stage_no,
                Reflection.giver_user_id,
                Reflection.receiver_user_id,
                Reflection.sender_name,
                Reflection.is_anonymous,  # Added this field
                CategoryDict.category_name
            ).join(
                CategoryDict,
                Reflection.category_no == CategoryDict.category_no,
                isouter=True
            ).filter(
                Reflection.reflection_id == reflection_uuid,
                # User can access if they are EITHER giver OR receiver
                or_(
                    Reflection.giver_user_id == current_user.user_id,
                    Reflection.receiver_user_id == current_user.user_id
                ),
                Reflection.status == 1
            ).first()
            
            if not reflection:
                return {
                    "success": False,
                    "message": "Reflection not found or access denied",
                    "data": {}
                }
            
            # Determine user's role in this reflection
            is_sender = (reflection.giver_user_id == current_user.user_id)
            user_role = "sent" if is_sender else "received"
            
            # Determine display name based on anonymity choice (for both senders and receivers)
            if reflection.is_anonymous is False and reflection.sender_name:
                display_name = reflection.sender_name
            elif reflection.is_anonymous is False and reflection.name:
                display_name = reflection.name  # Fallback to reflection.name
            else:
                display_name = "Anonymous"
            
            # Base response data (same for both sender and receiver)
            response_data = {
                "reflection_id": str(reflection.reflection_id),
                "name": reflection.name or "Unknown",
                "relation": reflection.relation or "",
                "category": reflection.category_name or "General",
                "summary": reflection.reflection or "No summary available",
                "created_at": reflection.created_at.isoformat() if reflection.created_at else None,
                "stage": reflection.stage_no,
                "user_role": user_role,
                "is_sender": is_sender,
                "sender_name": reflection.sender_name,
                "is_anonymous": reflection.is_anonymous,
                "display_name": display_name  # Frontend should use this for "From: ..."
            }
            
            # CONDITIONAL: Only add messages and conversation history for SENDERS
            if is_sender:
                # Get messages for conversation history (ONLY for senders)
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
                
                # Add full details for senders
                response_data.update({
                    "messages": message_list,
                    "giver_user_id": str(reflection.giver_user_id),
                    "receiver_user_id": str(reflection.receiver_user_id) if reflection.receiver_user_id else None,
                    "access_level": "full"  # Sender gets full access
                })
                
                logging.info(f"Sender {current_user.user_id} accessing full reflection {reflection_uuid}")
            
            else:
                # RECEIVERS: Only get summary - NO messages, NO conversation history
                response_data.update({
                    "access_level": "summary_only",  # Receiver gets summary only
                    "message": "You can only view the summary of reflections sent to you"
                })
                
                logging.info(f"Receiver {current_user.user_id} accessing summary-only for reflection {reflection_uuid}")
            
            return {
                "success": True,
                "message": "Reflection detail fetched",
                "data": response_data
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in get_reflection_history: {str(e)}")
        return {
            "success": False,
            "message": "Internal server error",
            "data": {}
        }