from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, Message, StageDict
from fastapi import HTTPException
import uuid


class Stage3(BaseStage):
    """Stage 3: Relationship input - Clean version without distress detection"""
    
    def get_stage_number(self) -> int:
        return 3
    
    def get_prompt(self) -> str:
        """Fetch prompt from existing stages_dict table"""
        stage = self.db.query(StageDict).filter(
            StageDict.stage_no == 3,
            StageDict.status == 1
        ).first()
        
        if not stage:
            raise HTTPException(status_code=500, detail="Stage 3 not found in database")
        
        return stage.prompt if stage.prompt else f"Please proceed with {stage.stage_name}"
    
    def get_transition_message(self, name: str, relation: str) -> str:
        """Build transition message to introduce the next stage"""
        return (
            f"Thanks for sharing your thoughts about {name} ({relation}). "
            f"I'm here to help you shape your message. Take your time and be honest — everything stays private between us."
            f"Take a breath, there's no rush. When you're ready, start anywhere. 😊"
        )
    
    async def process(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        reflection_id = uuid.UUID(request.reflection_id)
        
        relation = request.message.strip()
        if not relation:
            raise HTTPException(status_code=400, detail="Relationship cannot be empty.")
        
        if len(relation) > 256:
            raise HTTPException(status_code=400, detail="Relationship description is too long.")
        
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found or access denied")
        
        # Update reflection
        reflection.relation = relation
        reflection.stage_no = 3
        
        # Save user message
        message = Message(
            text=request.message,
            reflection_id=reflection_id,
            sender=1,
            stage_no=3
        )
        self.db.add(message)
        self.db.commit()
        
        # Compose transition message to Stage 4
        transition_message = self.get_transition_message(reflection.name, relation)

        transition_msg = Message(
        text=transition_message,
        reflection_id=reflection_id,
        sender=0,  # Assistant
        stage_no=3
    )
        self.db.add(transition_msg)

        self.db.commit()
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=transition_message,
            current_stage=3,
            next_stage=4,  # Move forward to Stage 4
            progress=ProgressInfo(
                current_step=4,
                total_step=5,
                workflow_completed=False  # Continue to conversation stage
            ),
            data=[]
        )
