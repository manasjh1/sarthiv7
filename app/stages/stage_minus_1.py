from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, Message, StageDict
from fastapi import HTTPException
import uuid

class StageMinus1(BaseStage):
    """Stage -1: Distress/Crisis handling stage"""
    
    def get_stage_number(self) -> int:
        return -1
    
    def get_prompt(self) -> str:
        """Get distress prompt from database - stage_no = -1"""
        stage = self.db.query(StageDict).filter(
            StageDict.stage_no == -1,
            StageDict.status == 1
        ).first()
        
        if not stage:
            raise HTTPException(status_code=500, detail="Distress stage (-1) not found in database")
        
        # Return the prompt from database, fallback to stage_name if prompt is empty
        return stage.prompt if stage.prompt else f"Crisis mode: {stage.stage_name}"
    
    async def process(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """
        Process distress stage - User is in crisis mode
        Gets prompt from database (stage_no = -1)
        """
        reflection_id = uuid.UUID(request.reflection_id)
        
        # Verify reflection belongs to user
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found or access denied")
        
        # Update reflection to distress stage
        reflection.stage_no = -1
        
        # Save user message in distress stage
        message = Message(
            text=request.message,
            reflection_id=reflection_id,
            sender=1,  # User
            stage_no=-1,
            is_distress=True  # Always distress in this stage
        )
        self.db.add(message)
        
        # Get the crisis prompt from database (stage_no = -1)
        crisis_prompt = self.get_prompt()
        
        # Save system response with the database prompt
        system_message = Message(
            text=crisis_prompt,
            reflection_id=reflection_id,
            sender=0,  # System
            stage_no=-1
        )
        self.db.add(system_message)
        
        self.db.commit()
        
        return UniversalResponse(
            success=False,  # Indicates crisis mode
            reflection_id=str(reflection_id),  # Variables are defined above
            sarthi_message=crisis_prompt,  # Variables are defined above
            current_stage=-1,
            next_stage=-1,  # Stay in crisis stage
            progress=ProgressInfo(
                current_step=1,  # Fixed: was current_stage, should be current_step
                total_step=1,
                workflow_completed=False  # Crisis mode doesn't complete workflow
            ),
            data=[{
                "distress_level": "critical",  # Added missing comma
                "stage": "crisis",  # Added missing comma
                "blocked": True,
                "message": "User is in distress mode. Prompt retrieved from database.",  # Fixed typo
                "prompt_source": "database_stage_-1"
            }]
        )