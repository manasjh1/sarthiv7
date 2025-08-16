# app/stages/stage_minus_1.py - Complete Production Version
from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, Message, StageDict, DistressLog
from fastapi import HTTPException
import uuid
import logging

class StageMinus1(BaseStage):
    """Stage -1: Crisis support and intervention"""
    
    def __init__(self, db):
        super().__init__(db)
        self.logger = logging.getLogger(__name__)
    
    def get_stage_number(self) -> int:
        return -1
    
    def get_prompt(self) -> str:
        """Get crisis support prompt from database"""
        stage = self.db.query(StageDict).filter(
            StageDict.stage_no == -1,
            StageDict.status == 1
        ).first()
        
        if not stage or not stage.prompt:
            # Fallback crisis message if not found in database
            return ("I'm concerned about what you've shared. Your safety is important. "
                   "Please reach out to a crisis helpline: National Suicide Prevention Lifeline: 988 "
                   "or Emergency Services: 911. You don't have to go through this alone.")
        
        return stage.prompt
    
    async def process(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """
        Process crisis intervention stage
        
        This stage:
        1. Logs the distress incident
        2. Provides crisis support resources
        3. Blocks normal conversation flow
        4. Keeps user in crisis support mode
        """
        try:
            reflection_id = uuid.UUID(request.reflection_id)
            
            # Verify reflection exists and belongs to user
            reflection = self.db.query(Reflection).filter(
                Reflection.reflection_id == reflection_id,
                Reflection.giver_user_id == user_id
            ).first()
            
            if not reflection:
                raise HTTPException(status_code=404, detail="Reflection not found or access denied")
            
            # Update reflection to crisis stage
            reflection.stage_no = -1
            
            # Save user message with distress flag
            user_message = Message(
                text=request.message,
                reflection_id=reflection_id,
                sender=1,  # User
                stage_no=-1,
                is_distress=True
            )
            self.db.add(user_message)
            
            # Log distress incident for monitoring/analytics
            try:
                distress_log = DistressLog(
                    reflection_id=reflection_id,
                    message_id=user_message.message_id,
                    distress_level=1,  # Critical
                    user_id=user_id
                )
                self.db.add(distress_log)
                self.logger.info(f"Distress incident logged for user {user_id}")
            except Exception as log_error:
                self.logger.error(f"Failed to log distress incident: {str(log_error)}")
                # Continue even if logging fails
            
            # Get crisis support message from database
            crisis_message = self.get_prompt()
            
            # Save system crisis response
            system_message = Message(
                text=crisis_message,
                reflection_id=reflection_id,
                sender=0,  # System
                stage_no=-1,
                is_distress=False
            )
            self.db.add(system_message)
            
            self.db.commit()
            
            # Return crisis response - success=False indicates intervention
            return UniversalResponse(
                success=False,  # Important: False indicates crisis intervention
                reflection_id=str(reflection_id),
                sarthi_message=crisis_message,
                current_stage=-1,
                next_stage=-1,  # Stay in crisis stage
                progress=ProgressInfo(
                    current_step=1,
                    total_step=1,
                    workflow_completed=False
                ),
                data=[{
                    "distress_level": "critical",
                    "stage": "crisis_intervention",
                    "blocked": True,
                    "resources": {
                        "suicide_prevention": "988",
                        "emergency": "911",
                        "crisis_text": "Text HOME to 741741"
                    },
                    "message": "User has been redirected to crisis support"
                }]
            )
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error in crisis stage processing: {str(e)}")
            self.db.rollback()
            
            # Even if there's an error, provide crisis support
            return UniversalResponse(
                success=False,
                reflection_id=str(reflection_id) if 'reflection_id' in locals() else "",
                sarthi_message="I'm concerned about your safety. Please reach out for help: 988 (Suicide Prevention) or 911 (Emergency).",
                current_stage=-1,
                next_stage=-1,
                progress=ProgressInfo(current_step=1, total_step=1, workflow_completed=False),
                data=[{"distress_level": "critical", "error": "processing_error"}]
            )