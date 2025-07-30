from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, CategoryDict, Message, StageDict
from fastapi import HTTPException
import uuid

class Stage1(BaseStage):
    """Stage 1: Category selection from database"""
    
    def get_stage_number(self) -> int:
        return 1
    
    def get_prompt(self) -> str:
        """Get stage prompt from database and append categories"""
        # Get stage prompt from stages_dict.prompt field
        stage = self.db.query(StageDict).filter(
            StageDict.stage_no == 1,
            StageDict.status == 1
        ).first()
        
        if not stage or not stage.prompt:
            raise HTTPException(status_code=500, detail="Stage 1 prompt not found in database")
        
        # Get categories from database
        categories = self.db.query(CategoryDict).filter(
            CategoryDict.status == 1
        ).order_by(CategoryDict.category_no).all()
        
        if not categories:
            raise HTTPException(status_code=500, detail="No categories found in database")
        
        # Combine stage prompt with categories
        prompt = stage.prompt + "\n"
        for category in categories:
            prompt += f"{category.category_no}: {category.category_name}\n"
        
        return prompt.strip()
    
    def process(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process category selection and move to stage 2"""
        reflection_id = uuid.UUID(request.reflection_id)
        
        # Validate category selection from data field (not message)
        category_data = request.data[0] if request.data else {}
        category_no = category_data.get("category_no")  # Changed from category_id to category_no
        
        if not category_no:
            raise HTTPException(status_code=400, detail="Category selection required in data field")
        
        try:
            category_no = int(category_no)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid category_no format. Must be a number.")
        
        # Verify category exists in database
        category = self.db.query(CategoryDict).filter(
            CategoryDict.category_no == category_no,
            CategoryDict.status == 1
        ).first()
        
        if not category:
            raise HTTPException(status_code=400, detail="Invalid category selection. Please choose from available options.")
        
        # Verify reflection belongs to user
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found or access denied")
        
        # Update reflection with category and stage
        reflection.category_no = category_no
        reflection.stage_no = 1
        
        # Save user message (if any) - no distress detection needed for category selection
        if request.message:
            message = Message(
                text=request.message,  # User message only
                reflection_id=reflection_id,
                sender=1,  # User sender
                stage_no=1,
                is_distress=False  # Category selection is safe
            )
            self.db.add(message)
        
        self.db.commit()
        
        # Get stage 2 prompt from database
        from app.stages.stage_2 import Stage2
        stage2 = Stage2(self.db)
        next_prompt = stage2.get_prompt()
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=next_prompt,  # System prompt - not checked for distress
            current_stage=1,
            next_stage=2,
            progress=ProgressInfo(
                current_step=2,
                total_step=5,
                workflow_completed=False
            ),
            data=[]  # Empty data as requested
        )