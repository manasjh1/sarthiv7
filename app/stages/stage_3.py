from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, Message, StageDict
from fastapi import HTTPException
import uuid

class Stage3(BaseStage):
    """Stage 3: Relationship input and workflow completion"""
    
    def get_stage_number(self) -> int:
        return 3
    
    def get_prompt(self) -> str:
        """Fetch prompt from stages_dict.prompt field"""
        stage = self.db.query(StageDict).filter(
            StageDict.stage_no == 3,
            StageDict.status == 1
        ).first()
        
        if not stage or not stage.prompt:
            raise HTTPException(status_code=500, detail="Stage 3 prompt not found in database")
        return stage.prompt
    
    def process(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process relationship input and complete workflow"""
        reflection_id = uuid.UUID(request.reflection_id)
        
        # Validate relationship input
        relation = request.message.strip()
        if not relation:
            raise HTTPException(status_code=400, detail="Relationship cannot be empty. Please enter a valid relationship.")
        
        if len(relation) > 256:
            raise HTTPException(status_code=400, detail="Relationship description is too long. Please enter a shorter description.")
        
        # Verify reflection belongs to user
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found or access denied")
        
        # Update reflection with relationship and complete stage
        reflection.relation = relation
        reflection.stage_no = 3
        
        # Save user message
        message = Message(
            text=request.message,
            reflection_id=reflection_id,
            sender=1,  # User sender
            stage_no=3
        )
        self.db.add(message)
        
        self.db.commit()
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message="Thank you! Your reflection has been completed successfully.",
            current_stage=3,
            next_stage=3,  # No next stage, workflow completed
            progress=ProgressInfo(
                current_step=4,
                total_step=4,
                workflow_completed=True
            )
        )
