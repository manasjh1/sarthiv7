# app/stage_handler.py
from typing import Dict, Any
from app.schemas import UniversalRequest, UniversalResponse
from app.models import Reflection, StageDict, CategoryDict, Message
from sqlalchemy.orm import Session
from fastapi import HTTPException
import uuid

class StageHandler:
    """Fully database-driven stage management"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_available_stages(self) -> list:
        """Get all available stages from database"""
        stages = self.db.query(StageDict).filter(
            StageDict.status == 1
        ).order_by(StageDict.stage_no).all()
        return stages
    
    def get_current_stage(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Get current stage number from reflection"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found")
        return reflection.stage_no
    
    def process_request(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Database-driven request processing"""
        try:
            # Handle initial request (no reflection_id)
            if not request.reflection_id:
                return self.create_new_reflection(request, user_id)
            
            # Get current stage and process next
            reflection_id = uuid.UUID(request.reflection_id)
            current_stage = self.get_current_stage(reflection_id, user_id)
            target_stage = current_stage + 1
            
            # Get stage info from database
            stage_info = self.db.query(StageDict).filter(
                StageDict.stage_no == target_stage,
                StageDict.status == 1
            ).first()
            
            if not stage_info:
                raise HTTPException(status_code=400, detail="Workflow completed")
            
            # Process based on stage type from database
            return self.process_stage(reflection_id, target_stage, request, user_id)
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    def create_new_reflection(self, request: UniversalRequest, user_id: uuid.UUID):
        """Create new reflection - Stage 0"""
        new_reflection = Reflection(
            giver_user_id=user_id,
            stage_no=0,
            status=1
        )
        self.db.add(new_reflection)
        self.db.commit()
        self.db.refresh(new_reflection)
        
        # Get next stage prompt from database
        next_stage = self.db.query(StageDict).filter(
            StageDict.stage_no == 1,
            StageDict.status == 1
        ).first()
        
        if not next_stage:
            raise HTTPException(status_code=500, detail="No stages configured")
        
        # For stage 1, add categories if it's category selection
        prompt = next_stage.prompt
        if next_stage.stage_no == 1:  # Category selection stage
            categories = self.db.query(CategoryDict).filter(
                CategoryDict.status == 1
            ).order_by(CategoryDict.category_no).all()
            
            if categories:
                prompt += "\n"
                for cat in categories:
                    prompt += f"{cat.category_no}: {cat.category_name}\n"
                prompt = prompt.strip()
        
        return self.build_response(
            success=True,
            reflection_id=str(new_reflection.reflection_id),
            message=prompt,
            current_stage=0,
            next_stage=1,
            current_step=1,
            total_step=4,
            completed=False
        )
    
    def process_stage(self, reflection_id: uuid.UUID, stage_no: int, request: UniversalRequest, user_id: uuid.UUID):
        """Process any stage based on database configuration"""
        
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found")
        
        # Database-driven stage processing
        if stage_no == 1:  # Category selection
            return self.process_category_stage(reflection, request)
        elif stage_no == 2:  # Name input
            return self.process_name_stage(reflection, request)
        elif stage_no == 3:  # Relationship input
            return self.process_relationship_stage(reflection, request)
        else:
            raise HTTPException(status_code=400, detail="Invalid stage")
    
    def process_category_stage(self, reflection: Reflection, request: UniversalRequest):
        """Process category selection"""
        try:
            category_no = int(request.message.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid category")
        
        # Validate category exists
        category = self.db.query(CategoryDict).filter(
            CategoryDict.category_no == category_no,
            CategoryDict.status == 1
        ).first()
        
        if not category:
            raise HTTPException(status_code=400, detail="Invalid category selection")
        
        # Update reflection
        reflection.category_no = category_no
        reflection.stage_no = 1
        
        # Save message
        message = Message(
            text=request.message,
            reflection_id=reflection.reflection_id,
            sender=1,
            stage_no=1
        )
        self.db.add(message)
        self.db.commit()
        
        # Get next stage prompt
        next_stage = self.db.query(StageDict).filter(
            StageDict.stage_no == 2,
            StageDict.status == 1
        ).first()
        
        return self.build_response(
            success=True,
            reflection_id=str(reflection.reflection_id),
            message=next_stage.prompt if next_stage else "Next stage not found",
            current_stage=1,
            next_stage=2,
            current_step=2,
            total_step=4,
            completed=False
        )
    
    def process_name_stage(self, reflection: Reflection, request: UniversalRequest):
        """Process name input"""
        name = request.message.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        
        # Update reflection
        reflection.name = name
        reflection.stage_no = 2
        
        # Save message
        message = Message(
            text=request.message,
            reflection_id=reflection.reflection_id,
            sender=1,
            stage_no=2
        )
        self.db.add(message)
        self.db.commit()
        
        # Get next stage prompt
        next_stage = self.db.query(StageDict).filter(
            StageDict.stage_no == 3,
            StageDict.status == 1
        ).first()
        
        return self.build_response(
            success=True,
            reflection_id=str(reflection.reflection_id),
            message=next_stage.prompt if next_stage else "Next stage not found",
            current_stage=2,
            next_stage=3,
            current_step=3,
            total_step=4,
            completed=False
        )
    
    def process_relationship_stage(self, reflection: Reflection, request: UniversalRequest):
        """Process relationship input"""
        relation = request.message.strip()
        if not relation:
            raise HTTPException(status_code=400, detail="Relationship cannot be empty")
        
        # Update reflection
        reflection.relation = relation
        reflection.stage_no = 3
        
        # Save message
        message = Message(
            text=request.message,
            reflection_id=reflection.reflection_id,
            sender=1,
            stage_no=3
        )
        self.db.add(message)
        self.db.commit()
        
        return self.build_response(
            success=True,
            reflection_id=str(reflection.reflection_id),
            message="Thank you! Your reflection has been completed successfully.",
            current_stage=3,
            next_stage=3,
            current_step=4,
            total_step=4,
            completed=True
        )
    
    def build_response(self, success: bool, reflection_id: str, message: str, 
                      current_stage: int, next_stage: int, current_step: int, 
                      total_step: int, completed: bool) -> UniversalResponse:
        """Build standardized response"""
        from app.schemas import ProgressInfo
        
        return UniversalResponse(
            success=success,
            reflection_id=reflection_id,
            sarthi_message=message,
            current_stage=current_stage,
            next_stage=next_stage,
            progress=ProgressInfo(
                current_step=current_step,
                total_step=total_step,
                workflow_completed=completed
            )
        )