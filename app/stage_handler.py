# app/stage_handler.py
from typing import Dict, Any, List
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, StageDict, CategoryDict, Message
from sqlalchemy.orm import Session
from fastapi import HTTPException
import uuid

class StageHandler:
    """Fully database-driven stage management with new API structure"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def process_request(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Database-driven request processing with new API structure"""
        try:
            # Handle initial request (no reflection_id) - Stage 0
            if not request.reflection_id:
                return self.create_new_reflection(request, user_id)
            
            # Get current stage and process next
            reflection_id = uuid.UUID(request.reflection_id)
            current_stage = self.get_current_stage(reflection_id, user_id)
            target_stage = current_stage + 1
            
            # Process based on target stage
            if target_stage == 1:
                return self.process_category_stage(reflection_id, request, user_id)
            elif target_stage == 2:
                return self.process_name_stage(reflection_id, request, user_id)
            elif target_stage == 3:
                return self.process_relationship_stage(reflection_id, request, user_id)
            else:
                raise HTTPException(status_code=400, detail="Workflow completed")
            
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid UUID format: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    def get_current_stage(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Get current stage number from reflection"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found")
        return reflection.stage_no
    
    def create_new_reflection(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Create new reflection - Stage 0"""
        new_reflection = Reflection(
            giver_user_id=user_id,
            stage_no=0,
            status=1
        )
        self.db.add(new_reflection)
        self.db.commit()
        self.db.refresh(new_reflection)
        
        # Get categories from database for response
        categories = self.db.query(CategoryDict).filter(
            CategoryDict.status == 1
        ).order_by(CategoryDict.category_no).all()
        
        if not categories:
            raise HTTPException(status_code=500, detail="No categories found")
        
        # Build categories data for response
        categories_data = []
        for cat in categories:
            categories_data.append({
                "category_no": cat.category_no,
                "category_name": cat.category_name
            })
        
        return UniversalResponse(
            success=True,
            reflection_id=str(new_reflection.reflection_id),
            sarthi_message="Hi, Welcome to Sarthi! Please select a category:",
            current_stage=0,
            next_stage=1,
            progress=ProgressInfo(
                current_step=1,
                total_step=4,
                workflow_completed=False
            ),
            data=categories_data
        )
    
    def process_category_stage(self, reflection_id: uuid.UUID, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process category selection - Stage 1"""
        try:
            reflection = self.db.query(Reflection).filter(
                Reflection.reflection_id == reflection_id,
                Reflection.giver_user_id == user_id
            ).first()
            
            if not reflection:
                raise HTTPException(status_code=404, detail="Reflection not found")
            
            # Extract category from data array
            category_no = None
            category_name = None
            
            if request.data and len(request.data) > 0:
                category_data = request.data[0]
                category_no = category_data.get("Category_no")
                category_name = category_data.get("Category_name")
            
            if not category_no:
                raise HTTPException(status_code=400, detail="Category selection required")
            
            # Validate category exists in database
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
                text=request.message if request.message else "",
                reflection_id=reflection_id,
                sender=1,
                stage_no=1
            )
            self.db.add(message)
            self.db.commit()
            
            # Build response data - use the category_name from database to ensure consistency
            response_data = [{
                "selected_category": category_no,
                "Category_name": category.category_name
            }]
            
            return UniversalResponse(
                success=True,
                reflection_id=str(reflection_id),
                sarthi_message=f"Great! You selected {category.category_name}. Please enter the name of the person:",
                current_stage=1,
                next_stage=2,
                progress=ProgressInfo(
                    current_step=2,
                    total_step=4,
                    workflow_completed=False
                ),
                data=response_data
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing category stage: {str(e)}")
    
    def process_name_stage(self, reflection_id: uuid.UUID, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process name input - Stage 2"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found")
        
        name = request.message.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        
        # Update reflection
        reflection.name = name
        reflection.stage_no = 2
        
        # Save message
        message = Message(
            text=request.message,
            reflection_id=reflection_id,
            sender=1,
            stage_no=2
        )
        self.db.add(message)
        self.db.commit()
        
        # Build response data
        response_data = [{
            "name": name
        }]
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=f"Thank you! What is your relationship with {name}?",
            current_stage=2,
            next_stage=3,
            progress=ProgressInfo(
                current_step=3,
                total_step=4,
                workflow_completed=False
            ),
            data=response_data
        )
    
    def process_relationship_stage(self, reflection_id: uuid.UUID, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process relationship input - Stage 3 (Final)"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found")
        
        relation = request.message.strip()
        if not relation:
            raise HTTPException(status_code=400, detail="Relationship cannot be empty")
        
        # Update reflection
        reflection.relation = relation
        reflection.stage_no = 3
        
        # Save message
        message = Message(
            text=request.message,
            reflection_id=reflection_id,
            sender=1,
            stage_no=3
        )
        self.db.add(message)
        self.db.commit()
        
        # Build response data
        response_data = [{
            "relationship": relation.lower()
        }]
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=f"Perfect! Your feedback for {reflection.name} {relation} has been recorded successfully.",
            current_stage=3,
            next_stage=3,
            progress=ProgressInfo(
                current_step=4,
                total_step=4,
                workflow_completed=True
            ),
            data=response_data
        )