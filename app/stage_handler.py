# app/stage_handler.py - Production Level Complete Implementation

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
    
    This class manages the flow between different stages of the reflection process:
    - Stage 0: Category selection
    - Stage 1: Category confirmation 
    - Stage 2: Name input
    - Stage 3: Relationship input
    - Stage 4: Conversation and summary generation
    - Stage 100: Identity reveal, delivery, and feedback
    - Stage -1: Distress handling
    
    Features:
    - Centralized distress detection for stages 2, 3, 4
    - Robust error handling and logging
    - Production-level validation
    - Clean separation of concerns
    """

    def __init__(self, db: Session):
        """
        Initialize Stage Handler
        
        Args:
            db: Database session
        """
        self.db = db
        self.distress_detector = DistressDetector()
        self.logger = logging.getLogger(__name__)

    async def check_distress(self, message: str) -> int:
        """
        Check distress level asynchronously - only on user messages
        
        Args:
            message: User message to analyze
            
        Returns:
            int: Distress level (0=no distress, 1=critical distress)
        """
        try:
            return await self.distress_detector.check(message)
        except Exception as e:
            self.logger.error(f"Distress detection error: {str(e)}")
            return 0  # Default to no distress on error

    def get_stage_prompt(self, stage_no: int) -> str:
        """
        Get stage prompt from database
        
        Args:
            stage_no: Stage number
            
        Returns:
            str: Stage prompt text
            
        Raises:
            HTTPException: If stage not found
        """
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
        """
        Redirect user to stage -1 (distress stage) when critical distress is detected
        
        Args:
            reflection_id: UUID of the reflection
            request: User request
            user_id: UUID of the user
            current_stage: Current stage number
            
        Returns:
            UniversalResponse: Distress stage response
        """
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
        """
        Main entry point with centralized async distress detection
        
        Args:
            request: Universal request from user
            user_id: UUID of the user
            
        Returns:
            UniversalResponse: Appropriate response based on stage
            
        Raises:
            HTTPException: For various error conditions
        """
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
                return await self._handle_stage4_edit_mode(request, user_id)
            
            # Handle Stage 100 (delivery, identity reveal, feedback)
            if current_stage == 100:
                self.logger.info("Processing Stage 100 - identity reveal, delivery, and feedback")
                stage = Stage100(self.db)
                return await stage.handle(request, user_id)
            
            # Handle Stage 4 completion/continuation
            if current_stage == 4:
                self.logger.info("Processing Stage 4 completion/continuation")
                return await self.handle_stage4_completion(reflection_id, request, user_id)
            
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
            
            # ================================================================
            
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

    async def _handle_stage4_edit_mode(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Handle Stage 4 edit mode (regenerate/edit)"""
        stage = Stage4(self.db)
        try:
            response = await stage.process(request, user_id)
            return response
        finally:
            await stage.close()  # Clean up async client

    async def _route_to_stage(
        self, 
        target_stage: int, 
        reflection_id: uuid.UUID, 
        request: UniversalRequest, 
        user_id: uuid.UUID,
        distress_level: int
    ) -> UniversalResponse:
        """
        Route request to appropriate stage handler
        
        Args:
            target_stage: Target stage number
            reflection_id: Reflection UUID
            request: User request
            user_id: User UUID
            distress_level: Detected distress level
            
        Returns:
            UniversalResponse: Stage-specific response
        """
        if target_stage == 1:
            return self.process_category_stage(reflection_id, request, user_id)
        elif target_stage == 2:
            return self.process_name_stage(reflection_id, request, user_id, distress_level)
        elif target_stage == 3:
            return self.process_relationship_stage(reflection_id, request, user_id, distress_level)
        elif target_stage == 4:
            return await self.process_conversation_stage(reflection_id, request, user_id, distress_level)
        else:
            self.logger.warning(f"Workflow completed or invalid target stage: {target_stage}")
            raise HTTPException(status_code=400, detail="Workflow completed or invalid stage")
    
    def get_current_stage(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """
        Get current stage from reflection
        
        Args:
            reflection_id: Reflection UUID
            user_id: User UUID
            
        Returns:
            int: Current stage number
            
        Raises:
            HTTPException: If reflection not found
        """
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()

        if not reflection:
            self.logger.error(f"Reflection {reflection_id} not found for user {user_id}")
            raise HTTPException(status_code=404, detail="Reflection not found")

        return reflection.stage_no

    def create_new_reflection(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """
        Create new reflection and return categories
        
        Args:
            request: User request
            user_id: User UUID
            
        Returns:
            UniversalResponse: Categories selection response
            
        Raises:
            HTTPException: If no categories found
        """
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
        """
        Process category selection - Stage 1
        
        Args:
            reflection_id: Reflection UUID
            request: User request
            user_id: User UUID
            
        Returns:
            UniversalResponse: Stage 2 transition response
            
        Raises:
            HTTPException: For validation errors
        """
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
        """
        Process name input - Stage 2 (distress already checked)
        
        Args:
            reflection_id: Reflection UUID
            request: User request
            user_id: User UUID
            distress_level: Pre-checked distress level
            
        Returns:
            UniversalResponse: Stage 3 transition response
        """
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
        """
        Process relationship input - Stage 3 (distress already checked)
        
        Args:
            reflection_id: Reflection UUID
            request: User request
            user_id: User UUID
            distress_level: Pre-checked distress level
            
        Returns:
            UniversalResponse: Stage 4 transition response
        """
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

    async def process_conversation_stage(
        self, 
        reflection_id: uuid.UUID, 
        request: UniversalRequest, 
        user_id: uuid.UUID,
        distress_level: int = 0
    ) -> UniversalResponse:
        """
        Process conversation - Stage 4 (distress already checked)
        
        Args:
            reflection_id: Reflection UUID
            request: User request
            user_id: User UUID
            distress_level: Pre-checked distress level
            
        Returns:
            UniversalResponse: Stage 4 or Stage 100 response
        """
        try:
            self.logger.info(f"Processing conversation stage - distress level: {distress_level}")
            
            stage = Stage4(self.db)
            response = await stage.process(request, user_id)
            await stage.close()  # Clean up async client
            
            # Check for edit_mode to handle regenerate/edit differently
            edit_mode = self._extract_edit_mode(request.data)
            
            # Check if Stage 4 completed (summary generated, regenerated, or edited)
            if response.next_stage == 100:
                self.logger.info("Stage 4 completed, updating reflection stage to 100")
                
                # Update the reflection stage to 100 in database
                reflection = self._get_reflection(reflection_id, user_id)
                if reflection.stage_no != 100:
                    reflection.stage_no = 100
                    self.db.commit()
                    self.logger.info(f"Reflection stage updated to 100 for reflection_id: {reflection_id}")
                
                # Handle different completion modes
                response = self._handle_stage4_completion_modes(
                    response, edit_mode, reflection_id, user_id
                )
            
            # Add distress level info only for normal conversations (not regenerate/edit)
            if edit_mode not in ["regenerate", "edit"]:
                self._add_distress_info_to_response(response, distress_level)
                    
            return response
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error in process_conversation_stage: {str(e)}")
            raise HTTPException(status_code=500, detail="Conversation processing failed")

    def _handle_stage4_completion_modes(
        self, 
        response: UniversalResponse, 
        edit_mode: Optional[str], 
        reflection_id: uuid.UUID, 
        user_id: uuid.UUID
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
            # Normal completion - Show summary and transition to identity reveal
            self.logger.info("Normal Stage 4 completion - transitioning to identity reveal")
            
            updated_reflection = self._get_reflection(reflection_id, user_id)
            
            response.sarthi_message = (
                f"Perfect! Your reflection summary is ready:\n\n"
                f"\"{updated_reflection.reflection}\"\n\n"
                f"Now, let's prepare to deliver your message. "
                f"Would you like to reveal your name or send it anonymously?"
            )
            response.current_stage = 100
            response.next_stage = 100
            response.progress = ProgressInfo(current_step=5, total_step=6, workflow_completed=False)
            
            # Add identity reveal options
            identity_data = {
                "summary": updated_reflection.reflection,
                "next_step": "identity_reveal",
                "options": [
                    {"reveal_name": True, "label": "Reveal my name"},
                    {"reveal_name": False, "label": "Send anonymously"}
                ]
            }
            
            if isinstance(response.data, list):
                response.data.append(identity_data)
            else:
                response.data = [identity_data]
        
        return response

    def _add_distress_info_to_response(self, response: UniversalResponse, distress_level: int):
        """Add distress level information to response data"""
        distress_info = {"distress_level": distress_level}
        
        if isinstance(response.data, list):
            response.data.append(distress_info)
        else:
            response.data = [distress_info]

    async def handle_stage4_completion(
        self, 
        reflection_id: uuid.UUID, 
        request: UniversalRequest, 
        user_id: uuid.UUID
    ) -> UniversalResponse:  
        """
        Handle stage 4 completion and transition to Stage 100
        
        Args:
            reflection_id: Reflection UUID
            request: User request
            user_id: User UUID
            
        Returns:
            UniversalResponse: Appropriate response based on completion status
        """
        try:
            self.logger.info("Handling Stage 4 completion/continuation")
            
            reflection = self._get_reflection(reflection_id, user_id)
            
            # If summary already exists, user is ready for Stage 100
            if reflection.reflection and reflection.reflection.strip():
                self.logger.info("Summary exists, transitioning to Stage 100")
                
                # Update stage to 100 if not already
                if reflection.stage_no != 100:
                    reflection.stage_no = 100
                    self.db.commit()
                
                # Check if this is a specific Stage 100 request
                has_stage100_data = self._has_stage100_data(request.data)
                
                if has_stage100_data:
                    # User is actively engaging with Stage 100 flow
                    stage100 = Stage100(self.db)
                    return await stage100.handle(request, user_id)
                else:
                    # First time transitioning - show summary and options
                    return self._show_stage100_transition(reflection_id, reflection)
            else:
                self.logger.info("No summary yet, continuing Stage 4 conversation")
                return await self.process_conversation_stage(reflection_id, request, user_id)
        except Exception as e:
            self.logger.error(f"Error in handle_stage4_completion: {str(e)}")
            raise HTTPException(status_code=500, detail="Stage 4 completion handling failed")

    def _has_stage100_data(self, data: List[Dict[str, Any]]) -> bool:
        """Check if request contains Stage 100 specific data"""
        stage100_keys = ["reveal_name", "name", "delivery_mode", "email", "feedback"]
        return any(
            key in item for item in data 
            for key in stage100_keys
        )

    def _show_stage100_transition(self, reflection_id: uuid.UUID, reflection: Reflection) -> UniversalResponse:
        """Show Stage 100 transition with summary and identity options"""
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=(
                f"Perfect! Your reflection summary is ready:\n\n"
                f"\"{reflection.reflection}\"\n\n"
                f"Now, let's prepare to deliver your message. "
                f"Would you like to reveal your name or send it anonymously?"
            ),
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=5, total_step=6, workflow_completed=False),
            data=[{
                "summary": reflection.reflection,
                "next_step": "identity_reveal",
                "options": [
                    {"reveal_name": True, "label": "Reveal my name"},
                    {"reveal_name": False, "label": "Send anonymously"}
                ]
            }]
        )

    def _get_reflection(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> Reflection:
        """
        Get and validate reflection from database
        
        Args:
            reflection_id: Reflection UUID
            user_id: User UUID
            
        Returns:
            Reflection: Reflection object
            
        Raises:
            HTTPException: If reflection not found
        """
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()

        if not reflection:
            self.logger.error(f"Reflection {reflection_id} not found for user {user_id}")
            raise HTTPException(status_code=404, detail="Reflection not found")

        return reflection

    def get_completion_message(self, name: str, relation: str) -> str:
        """
        Get completion message from database (legacy method - kept for compatibility)
        
        Args:
            name: Person's name
            relation: Relationship
            
        Returns:
            str: Completion message
        """
        try:
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
        except Exception as e:
            self.logger.error(f"Error getting completion message: {str(e)}")
            return "Thank you for completing your reflection with Sarthi."