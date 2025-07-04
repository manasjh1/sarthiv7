from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, Message, StageDict
from fastapi import HTTPException
import uuid

class Stage2(BaseStage):
    """Stage 2: Person name input - Clean version without distress detection"""
    
    def get_stage_number(self) -> int:
        return 2
    
    def get_prompt(self) -> str:
        """Fetch prompt from existing stages_dict table"""
        stage = self.db.query(StageDict).filter(
            StageDict.stage_no == 2,
            StageDict.status == 1
        ).first()
        
        if not stage:
            raise HTTPException(status_code=500, detail="Stage 2 not found in database")
        
        # Use prompt if available, otherwise use stage_name as fallback
        if stage.prompt:
            return stage.prompt
        else:
            return f"Please proceed with {stage.stage_name}"
    
    def get_next_stage_prompt(self) -> str:
        """Get next stage (stage 3) prompt from existing database"""
        next_stage = self.db.query(StageDict).filter(
            StageDict.stage_no == 3,
            StageDict.status == 1
        ).first()
        
        if not next_stage:
            raise HTTPException(status_code=500, detail="Stage 3 not found in database")
        
        # Use prompt if available, otherwise use stage_name as fallback
        if next_stage.prompt:
            return next_stage.prompt
        else:
            return f"Please proceed with {next_stage.stage_name}"
    
    def process(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process name input - NO distress detection here (handled by stage_handler)"""
        reflection_id = uuid.UUID(request.reflection_id)
        
        # Validate name input
        name = request.message.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty. Please enter a valid name.")
        
        if len(name) > 256:
            raise HTTPException(status_code=400, detail="Name is too long. Please enter a shorter name.")
        
        # Verify reflection belongs to user
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found or access denied")
        
        # Update reflection with name and stage
        reflection.name = name
        reflection.stage_no = 2
        
        # Save user message - distress detection and is_distress flag handled by stage_handler
        message = Message(
            text=request.message,
            reflection_id=reflection_id,
            sender=1,  # User sender
            stage_no=2
            # Note: is_distress field will be set by stage_handler before calling this
        )
        self.db.add(message)
        self.db.commit()
        
        # Get stage 3 prompt from existing database
        next_prompt = self.get_next_stage_prompt()
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=next_prompt,
            current_stage=2,
            next_stage=3,
            progress=ProgressInfo(
                current_step=3,
                total_step=4,
                workflow_completed=False
            ),
            data=[]
        )