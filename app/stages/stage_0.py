from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, StageDict
from fastapi import HTTPException
import uuid

class Stage0(BaseStage):
    """Stage 0: Initial stage - creates reflection and starts journey"""
    
    def get_stage_number(self) -> int:
        return 0
    
    def get_prompt(self) -> str:
        """Fetch prompt from stages_dict.prompt field"""
        stage = self.db.query(StageDict).filter(
            StageDict.stage_no == 0,
            StageDict.status == 1
        ).first()
        
        if not stage or not stage.prompt:
            raise HTTPException(status_code=500, detail="Stage 0 prompt not found in database")
        return stage.prompt
    
    def process(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Create new reflection and move to stage 1"""
        # Create new reflection for stage 0
        new_reflection = Reflection(
            giver_user_id=user_id,
            stage_no=0,
            status=1
        )
        
        self.db.add(new_reflection)
        self.db.commit()
        self.db.refresh(new_reflection)
        
        # Get stage 1 prompt from database
        from app.stages.stage_1 import Stage1
        stage1 = Stage1(self.db)
        next_prompt = stage1.get_prompt()
        
        return UniversalResponse(
            success=True,
            reflection_id=str(new_reflection.reflection_id),
            sarthi_message=next_prompt,
            current_stage=0,
            next_stage=1,
            progress=ProgressInfo(
                current_step=1,
                total_step=4,
                workflow_completed=False
            )
        )