from typing import List
import uuid
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, StageDict, CategoryDict, Message
from app.stages.stage_4 import Stage4
from app.stages.stage_3 import Stage3
from app.stages.stage_100 import Stage100  
from app.stages.stage_minus_1 import StageMinus1
from distress_detection import DistressDetector

class StageHandler:
    """Database-driven stage handling with centralized distress detection for all stages"""

    def __init__(self, db: Session):
        self.db = db
        self.distress_detector = DistressDetector()

    def check_distress(self, message: str) -> int:
        """Check distress only on user messages"""
        try:
            return self.distress_detector.check(message)
        except Exception as e:
            print(f"Distress detection error: {str(e)}")
            return 0

    def get_stage_prompt(self, stage_no: int) -> str:
        stage = self.db.query(StageDict).filter(
            StageDict.stage_no == stage_no,
            StageDict.status == 1
        ).first()

        if not stage:
            raise HTTPException(status_code=500, detail=f"Stage {stage_no} not found in database")

        return stage.prompt or f"Please proceed with {stage.stage_name}"

    def handle_distress_redirect(self, reflection_id: uuid.UUID, request: UniversalRequest, user_id: uuid.UUID, current_stage: int) -> UniversalResponse:
        """ 
        Redirect user to stage -1 (distress stage) when critical distress is detected
        """
        print(f"Redirecting user to distress stage from stage {current_stage}")
        
        # Fixed: changed user_id to giver_user_id to match your model
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id  # Fixed: was user_id
        ).first()
        
        if reflection:
            reflection.stage_no = -1
            self.db.commit()
            
        distress_stage = StageMinus1(self.db)
        return distress_stage.process(request, user_id)   

    def process_request(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """
        Main entry point with centralized distress detection
        """
        try:
            if not request.reflection_id:
                return self.create_new_reflection(request, user_id)

            reflection_id = uuid.UUID(request.reflection_id)
            current_stage = self.get_current_stage(reflection_id, user_id)
            
            # Check if user is already in distress stage (-1)
            if current_stage == -1:
                print("User is already in distress stage, processing through Stage -1")
                distress_stage = StageMinus1(self.db)
                return distress_stage.process(request, user_id)
            
            # ================CENTRALIZED DISTRESS DETECTION==================#
            target_stage = current_stage + 1
            
            # Initialize distress_level to 0 by default
            distress_level = 0

            # Check if this is a regenerate or edit request - skip distress detection
            edit_mode = next((item.get("edit_mode") for item in request.data if "edit_mode" in item), None)
            
            if edit_mode in ["regenerate", "edit"]:
                print(f"Skipping distress detection for {edit_mode} request")
                distress_level = 0
            elif current_stage == 100:
                print("Stage 100 does not require distress checking")
                distress_level = 0
            elif target_stage in [2, 3, 4]: 
                print(f"Checking distress for stage {target_stage}")
                distress_level = self.check_distress(request.message)
                
                if distress_level == 1:
                    print(f"Critical distress detected in stage {target_stage}, redirecting to Stage -1")
                    return self.handle_distress_redirect(reflection_id, request, user_id, target_stage)
                
                print(f"No distress detected (level: {distress_level}), continuing to stage {target_stage}")
            else:
                print(f"Stage {target_stage} does not require distress checking")
            
            # ================================================================================================= #
            
            
            if target_stage == 1:
                return self.process_category_stage(reflection_id, request, user_id)
            elif target_stage == 2:
                return self.process_name_stage(reflection_id, request, user_id)
            elif target_stage == 3:
                return self.process_relationship_stage(reflection_id, request, user_id)
            elif target_stage == 4:
                return self.process_conversation_stage(reflection_id, request, user_id)
            elif current_stage == 100:  
                stage = Stage100(self.db)  
                return stage.handle(request, user_id)
            else:
                raise HTTPException(status_code=400, detail="Workflow completed")
        
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid UUID format: {str(e)}")
        except Exception as e:
            print(f"Unexpected error in process_request: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    def get_current_stage(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Get current stage from reflection"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()

        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found")

        return reflection.stage_no

    def create_new_reflection(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Create new reflection and return categories"""
        new_reflection = Reflection(
            giver_user_id=user_id,
            stage_no=0,
            status=1
        )
        self.db.add(new_reflection)
        self.db.commit()
        self.db.refresh(new_reflection)

        categories = self.db.query(CategoryDict).filter(
            CategoryDict.status == 1
        ).order_by(CategoryDict.category_no).all()

        if not categories:
            raise HTTPException(status_code=500, detail="No categories found")

        categories_data = [
            {"category_no": c.category_no, "category_name": c.category_name}
            for c in categories
        ]

        prompt = self.get_stage_prompt(0)

        return UniversalResponse(
            success=True,
            reflection_id=str(new_reflection.reflection_id),
            sarthi_message=prompt,
            current_stage=0,
            next_stage=1,
            progress=ProgressInfo(current_step=1, total_step=4, workflow_completed=False),
            data=categories_data
        )

    def process_category_stage(self, reflection_id: uuid.UUID, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process category selection - Stage 1"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()

        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found")

        
        print(f"Request data: {request.data}")
        
        category_data = request.data[0] if request.data else {}
        
        
        category_no = category_data.get("category_no")
        
        print(f"Extracted category_no: {category_no}")

        if not category_no:
            raise HTTPException(status_code=400, detail=f"Category selection required. Expected 'category_no' in data. Received data: {category_data}")

        
        try:
            category_no = int(category_no)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"Invalid category_no format: {category_no}")

        category = self.db.query(CategoryDict).filter(
            CategoryDict.category_no == category_no,
            CategoryDict.status == 1
        ).first()

        if not category:
            raise HTTPException(status_code=400, detail="Invalid category selection")
        
        
        reflection.category_no = category_no
        reflection.stage_no = 1
        
        # Save message
        message = Message(
            text=request.message if request.message else "",
            reflection_id=reflection_id,
            sender=1,
            stage_no=1,
            is_distress=False
        )
        self.db.add(message)
        self.db.commit()
         
        # Get stage 2 prompt
        response_data = []
        prompt = self.get_stage_prompt(2)
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=prompt,
            current_stage=1,
            next_stage=2,
            progress=ProgressInfo(current_step=2, total_step=4, workflow_completed=False),
            data=response_data
        )

    def process_name_stage(self, reflection_id: uuid.UUID, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process name input - Stage 2 (distress already checked)"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()

        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found")

        name = request.message.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")

        
        print("Processing name stage - distress already checked")
        
        
        
        reflection.name = name
        reflection.stage_no = 2
        
        # Save message
        self.db.add(Message(
            text=request.message,
            reflection_id=reflection_id,
            sender=1,
            stage_no=2,
            is_distress=False  
        ))
        self.db.commit()

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=self.get_stage_prompt(3),
            current_stage=2,
            next_stage=3,
            progress=ProgressInfo(current_step=3, total_step=4, workflow_completed=False),
            data=[{"distress_level": 0}]  
        )

    def process_relationship_stage(self, reflection_id: uuid.UUID, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process relationship input - Stage 3 (distress already checked)"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()

        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found")

        relation = request.message.strip()
        if not relation:
            raise HTTPException(status_code=400, detail="Relationship cannot be empty")

        
        print("Processing relationship stage - distress already checked")
        
        
        reflection.relation = relation
        reflection.stage_no = 3

        self.db.add(Message(
            text=request.message,
            reflection_id=reflection_id,
            sender=1,
            stage_no=3,
            is_distress=False  
        ))
        self.db.commit()

        stage3 = Stage3(self.db)
        transition_message = stage3.get_transition_message(reflection.name, relation)

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=transition_message,
            current_stage=3,
            next_stage=4,
            progress=ProgressInfo(current_step=4, total_step=4, workflow_completed=False),
            data=[{"distress_level": 0}]  
        )

    def process_conversation_stage(self, reflection_id: uuid.UUID, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """
        Process conversation - Stage 4 (distress already checked)
        """
        
        print("Processing conversation stage - distress already checked")
        
        
        stage = Stage4(self.db)
        response = stage.process(request, user_id)
        
        
        if isinstance(response.data, list):
            response.data.append({"distress_level": 0})  
        else:
            response.data = [{"distress_level": 0}]
            
        return response        

    def get_completion_message(self, name: str, relation: str) -> str:
        """Get completion message from database"""
        stage = self.db.query(StageDict).filter(
            StageDict.stage_name.ilike('%completion%'),
            StageDict.status == 1
        ).first()

        if stage and stage.prompt:
            try:
                return stage.prompt.format(name=name, relation=relation)
            except Exception:
                return stage.prompt

        return f"Perfect! Your feedback for {name} ({relation}) has been recorded successfully. Thank you for using Sarthi."