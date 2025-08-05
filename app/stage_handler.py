# app/stage_handler.py - FIXED - Proper Stage 4 Chat Initialization

from typing import List, Optional, Dict, Any
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
import logging


class StageHandler:
    """
    Production-level Stage Handler with centralized async distress detection
    FIXED: Proper Stage 4 initialization and summary display
    """

    def __init__(self, db: Session):
        """Initialize Stage Handler"""
        self.db = db
        self.distress_detector = DistressDetector()
        self.logger = logging.getLogger(__name__)

    async def check_distress(self, message: str) -> int:
        """Check distress level asynchronously - only on user messages"""
        try:
            return await self.distress_detector.check(message)
        except Exception as e:
            self.logger.error(f"Distress detection error: {str(e)}")
            return 0  # Default to no distress on error

    def get_stage_prompt(self, stage_no: int) -> str:
        """Get stage prompt from database"""
        stage = self.db.query(StageDict).filter(
            StageDict.stage_no == stage_no,
            StageDict.status == 1
        ).first()

        if not stage:
            self.logger.error(f"Stage {stage_no} not found in database")
            raise HTTPException(status_code=500, detail=f"Stage {stage_no} not found in database")

        return stage.prompt or f"Please proceed with {stage.stage_name}"

    async def handle_distress_redirect(
        self, 
        reflection_id: uuid.UUID, 
        request: UniversalRequest, 
        user_id: uuid.UUID, 
        current_stage: int
    ) -> UniversalResponse:
        """Redirect user to stage -1 (distress stage) when critical distress is detected"""
        self.logger.warning(f"Redirecting user {user_id} to distress stage from stage {current_stage}")
        
        try:
            reflection = self.db.query(Reflection).filter(
                Reflection.reflection_id == reflection_id,
                Reflection.giver_user_id == user_id 
            ).first()
            
            if reflection:
                reflection.stage_no = -1
                self.db.commit()
                self.logger.info(f"Reflection {reflection_id} stage updated to -1 (distress)")
                
            distress_stage = StageMinus1(self.db)
            return distress_stage.process(request, user_id)
        except Exception as e:
            self.logger.error(f"Error handling distress redirect: {str(e)}")
            raise HTTPException(status_code=500, detail="Error handling distress situation")

    async def process_request(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Main entry point with centralized async distress detection"""
        try:
            # Handle new reflection creation
            if not request.reflection_id:
                self.logger.info(f"Creating new reflection for user {user_id}")
                return self.create_new_reflection(request, user_id)

            reflection_id = uuid.UUID(request.reflection_id)
            current_stage = self.get_current_stage(reflection_id, user_id)
            
            self.logger.info(f"Processing request for reflection {reflection_id}, current stage: {current_stage}")
            
            # Handle distress stage
            if current_stage == -1:
                self.logger.info("User is in distress stage, processing through Stage -1")
                distress_stage = StageMinus1(self.db)
                return distress_stage.process(request, user_id)
            
            # Check for edit_mode FIRST (bypasses normal flow)
            edit_mode = self._extract_edit_mode(request.data)
            
            # If regenerate/edit request, always route to Stage4 regardless of current_stage
            if edit_mode in ["regenerate", "edit"]:
                self.logger.info(f"Edit mode '{edit_mode}' detected - routing to Stage4 regardless of current stage {current_stage}")
                return await self._handle_stage4_requests(request, user_id)
            
            # Handle Stage 100 (delivery, identity reveal, feedback)
            if current_stage == 100:
                self.logger.info("Processing Stage 100 - identity reveal, delivery, and feedback")
                stage = Stage100(self.db)
                return await stage.handle(request, user_id)
            
            # Handle Stage 4 (conversation or completion)
            if current_stage == 4:
                self.logger.info("Processing Stage 4 - guided conversation")
                return await self._handle_stage4_requests(request, user_id)
            
            # ========== CENTRALIZED ASYNC DISTRESS DETECTION ==========
            target_stage = current_stage + 1
            distress_level = 0
            
            # Only check distress for stages that involve user input about people/relationships
            if target_stage in [2, 3, 4]: 
                self.logger.debug(f"Checking distress for stage {target_stage}")
                distress_level = await self.check_distress(request.message)
                   
                if distress_level == 1:
                    self.logger.warning(f"Critical distress detected in stage {target_stage}")
                    return await self.handle_distress_redirect(reflection_id, request, user_id, target_stage)
                
                self.logger.debug(f"No distress detected (level: {distress_level})")
            else:
                self.logger.debug(f"Stage {target_stage} does not require distress checking")
            
            # Route to appropriate stage
            return await self._route_to_stage(target_stage, reflection_id, request, user_id, distress_level)
        
        except HTTPException:
            raise
        except ValueError as e:
            self.logger.error(f"UUID validation error: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid UUID format: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error in process_request: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")
        finally:
            # Always clean up async distress detector
            try:
                await self.distress_detector.close()
            except Exception as e:
                self.logger.error(f"Error closing distress detector: {str(e)}")

    def _extract_edit_mode(self, data: List[Dict[str, Any]]) -> Optional[str]:
        """Extract edit mode from request data"""
        return next((item.get("edit_mode") for item in data if "edit_mode" in item), None)

    async def _handle_stage4_requests(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Handle all Stage 4 requests (normal conversation, edit, regenerate)"""
        stage = Stage4(self.db)
        try:
            response = await stage.process(request, user_id)
            
            # Handle completion transition
            if response.next_stage == 100:
                self.logger.info("Stage 4 completed, updating reflection stage to 100")
                
                reflection_id = uuid.UUID(request.reflection_id)
                reflection = self._get_reflection(reflection_id, user_id)
                if reflection.stage_no != 100:
                    reflection.stage_no = 100
                    self.db.commit()
                    self.logger.info(f"Reflection stage updated to 100 for reflection_id: {reflection_id}")
                
                # Handle different completion modes
                edit_mode = self._extract_edit_mode(request.data)
                response = self._handle_stage4_completion_modes(response, edit_mode)
            
            return response
        finally:
            await stage.close()

    def _handle_stage4_completion_modes(
        self, 
        response: UniversalResponse, 
        edit_mode: Optional[str]
    ) -> UniversalResponse:
        """Handle different Stage 4 completion modes"""
        
        if edit_mode == "regenerate":
            self.logger.info("Regenerate request - preserving summary data")
            response.current_stage = 4
            response.next_stage = 100
            response.progress = ProgressInfo(current_step=4, total_step=6, workflow_completed=False)
            
        elif edit_mode == "edit":
            self.logger.info("Edit request - preserving edit confirmation")
            response.current_stage = 4
            response.next_stage = 100
            response.progress = ProgressInfo(current_step=4, total_step=6, workflow_completed=False)
            
        else:
            # Normal completion - transition to Stage 100
            self.logger.info("Normal Stage 4 completion - transitioning to identity reveal")
            response.current_stage = 100
            response.next_stage = 100
            response.progress = ProgressInfo(current_step=5, total_step=6, workflow_completed=False)
            # Keep the summary in data - don't clear it
        
        return response

    async def _route_to_stage(
        self, 
        target_stage: int, 
        reflection_id: uuid.UUID, 
        request: UniversalRequest, 
        user_id: uuid.UUID,
        distress_level: int
    ) -> UniversalResponse:
        """Route request to appropriate stage handler"""
        if target_stage == 1:
            return self.process_category_stage(reflection_id, request, user_id)
        elif target_stage == 2:
            return self.process_name_stage(reflection_id, request, user_id, distress_level)
        elif target_stage == 3:
            return self.process_relationship_stage(reflection_id, request, user_id, distress_level)
        elif target_stage == 4:
            return await self._handle_stage4_requests(request, user_id)
        else:
            self.logger.warning(f"Workflow completed or invalid target stage: {target_stage}")
            raise HTTPException(status_code=400, detail="Workflow completed or invalid stage")
    
    def get_current_stage(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Get current stage from reflection"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()

        if not reflection:
            self.logger.error(f"Reflection {reflection_id} not found for user {user_id}")
            raise HTTPException(status_code=404, detail="Reflection not found")

        return reflection.stage_no

    def create_new_reflection(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Create new reflection and return categories"""
        try:
            new_reflection = Reflection(
                giver_user_id=user_id,
                stage_no=0,
                status=1
            )
            self.db.add(new_reflection)
            self.db.commit()
            self.db.refresh(new_reflection)
            
            self.logger.info(f"Created new reflection {new_reflection.reflection_id} for user {user_id}")

            categories = self.db.query(CategoryDict).filter(
                CategoryDict.status == 1
            ).order_by(CategoryDict.category_no).all()

            if not categories:
                self.logger.error("No categories found in database")
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
                progress=ProgressInfo(current_step=1, total_step=6, workflow_completed=False),
                data=categories_data
            )
        except Exception as e:
            self.logger.error(f"Error creating new reflection: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Failed to create new reflection")

    def process_category_stage(self, reflection_id: uuid.UUID, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process category selection - Stage 1"""
        try:
            reflection = self._get_reflection(reflection_id, user_id)

            self.logger.debug(f"Request data: {request.data}")
            
            category_data = request.data[0] if request.data else {}
            category_no = category_data.get("category_no")
            
            if not category_no:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Category selection required. Expected 'category_no' in data. Received: {category_data}"
                )

            try:
                category_no = int(category_no)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail=f"Invalid category_no format: {category_no}")

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
                text=request.message if request.message else "",
                reflection_id=reflection_id,
                sender=1,
                stage_no=1,
                is_distress=False
            )
            self.db.add(message)
            self.db.commit()
            
            self.logger.info(f"Category {category_no} selected for reflection {reflection_id}")
             
            prompt = self.get_stage_prompt(2)
            
            return UniversalResponse(
                success=True,
                reflection_id=str(reflection_id),
                sarthi_message=prompt,
                current_stage=1,
                next_stage=2,
                progress=ProgressInfo(current_step=2, total_step=6, workflow_completed=False),
                data=[]
            )
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error in process_category_stage: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Category processing failed")

    def process_name_stage(
        self, 
        reflection_id: uuid.UUID, 
        request: UniversalRequest, 
        user_id: uuid.UUID,
        distress_level: int = 0
    ) -> UniversalResponse:
        """Process name input - Stage 2 (distress already checked)"""
        try:
            reflection = self._get_reflection(reflection_id, user_id)

            name = request.message.strip()
            if not name:
                raise HTTPException(status_code=400, detail="Name cannot be empty")

            self.logger.info(f"Processing name '{name}' for reflection {reflection_id} - distress level: {distress_level}")
            
            reflection.name = name
            reflection.stage_no = 2
            
            self.db.add(Message(
                text=request.message,
                reflection_id=reflection_id,
                sender=1,
                stage_no=2,
                is_distress=distress_level > 0
            ))
            self.db.commit()

            return UniversalResponse(
                success=True,
                reflection_id=str(reflection_id),
                sarthi_message=self.get_stage_prompt(3),
                current_stage=2,
                next_stage=3,
                progress=ProgressInfo(current_step=3, total_step=6, workflow_completed=False),
                data=[{"distress_level": distress_level}]
            )
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error in process_name_stage: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Name processing failed")

    def process_relationship_stage(
        self, 
        reflection_id: uuid.UUID, 
        request: UniversalRequest, 
        user_id: uuid.UUID,
        distress_level: int = 0
    ) -> UniversalResponse:
        """Process relationship input - Stage 3 (distress already checked)"""
        try:
            reflection = self._get_reflection(reflection_id, user_id)

            relation = request.message.strip()
            if not relation:
                raise HTTPException(status_code=400, detail="Relationship cannot be empty")

            self.logger.info(f"Processing relationship '{relation}' for reflection {reflection_id} - distress level: {distress_level}")
            
            reflection.relation = relation
            reflection.stage_no = 3

            self.db.add(Message(
                text=request.message,
                reflection_id=reflection_id,
                sender=1,
                stage_no=3,
                is_distress=distress_level > 0
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
                progress=ProgressInfo(current_step=4, total_step=6, workflow_completed=False),
                data=[{"distress_level": distress_level}]
            )
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error in process_relationship_stage: {str(e)}")
            self.db.rollback()
            raise HTTPException(status_code=500, detail="Relationship processing failed")

    def _get_reflection(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> Reflection:
        """Get and validate reflection from database"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()

        if not reflection:
            self.logger.error(f"Reflection {reflection_id} not found for user {user_id}")
            raise HTTPException(status_code=404, detail="Reflection not found")

        return reflection