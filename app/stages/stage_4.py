from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, Message, CategoryDict
from fastapi import HTTPException
from app.memory import get_buffer_memory
import uuid
from openai import AsyncOpenAI
import json
import os
from datetime import datetime

class Stage4(BaseStage):
    """
    Stage 4: Guided conversation with LLM (6-turn limit) with automatic summary generation
    
    FIXED: Always fetch summary from database for consistency
    - Summary saved to DB first
    - Then fetched from DB for response
    - Ensures data consistency across all scenarios
    """

    def __init__(self, db):
        super().__init__(db)
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def get_stage_number(self) -> int:
        return 4

    def get_prompt(self) -> str:
        return "This method is not used in Stage4."

    def get_system_prompt(self, reflection_id: uuid.UUID) -> str:
        """Get system prompt from CategoryDict table based on reflection's category"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id
        ).first()
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found")

        category = self.db.query(CategoryDict).filter(
            CategoryDict.category_no == reflection.category_no,
            CategoryDict.status == 1
        ).first()
        if not category or not category.system_prompt:
            raise HTTPException(status_code=500, detail="System prompt not found for this category")

        return category.system_prompt

    def get_user_input_count(self, history: list) -> int:
        """Simple count of user messages in the conversation"""
        return len([msg for msg in history if msg["role"] == "user"]) + 1

    def get_reflection_summary_from_db(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
        """
        CENTRALIZED: Always fetch summary from database
        Returns None if no summary exists
        """
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        
        if reflection and reflection.reflection and reflection.reflection.strip():
            return reflection.reflection
        return None

    async def generate_llm_response(self, system_prompt: str, history: list, user_input: str, backend_message: str = None) -> tuple[str, str | None]:
        """Generate LLM response asynchronously"""
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        
        # Add user message as plain text (consistent with history)
        messages.append({"role": "user", "content": user_input})
        
        user_count = self.get_user_input_count(history)
        backend_message_content = str(user_count)
        
        messages.append({
            "role": "system", 
            "content": backend_message_content  # Backend message with user count
        })

        try:
            # ASYNC OpenAI call
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            raw_reply = response.choices[0].message.content.strip()

            # Check for summary JSON response
            if "{" in raw_reply and "\"user\":" in raw_reply:
                try:
                    start_idx = raw_reply.find("{")
                    end_idx = raw_reply.rfind("}") + 1
                    if start_idx != -1 and end_idx > start_idx:
                        json_part = raw_reply[start_idx:end_idx]
                        parsed = json.loads(json_part)
                        if "user" in parsed:
                            return "__DONE__", json_part
                except (json.JSONDecodeError, ValueError):
                    pass

            # Check for system completion flag
            if raw_reply.startswith("{") and "system_flag" in raw_reply:
                try:
                    parsed = json.loads(raw_reply)
                    if parsed.get("system_flag") == "__DONE__":
                        return "__DONE__", None
                except json.JSONDecodeError:
                    pass

            return "", raw_reply
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM Error: {str(e)}")

    async def process_edit_mode(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Handle edit and regenerate modes - ALWAYS fetch summary from DB"""
        reflection_id = uuid.UUID(request.reflection_id)
        
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found or access denied")

        edit_mode = next((item.get("edit_mode") for item in request.data if "edit_mode" in item), None)

        if edit_mode == "edit":
            from distress_detection import DistressDetector
            distress_detector = DistressDetector()
            
            user_message = request.message.strip()
            if not user_message:
                raise HTTPException(status_code=400, detail="Message is required for edit mode")
            
            # ASYNC distress check
            distress = await distress_detector.check(user_message)
            await distress_detector.close()

            if distress == 1:
                raise HTTPException(status_code=400, detail="Distress detected in custom message")

            # 1. SAVE to database
            reflection.reflection = user_message
            reflection.stage_no = 4
            reflection.updated_at = datetime.utcnow()
            self.db.commit()

            # 2. FETCH from database for consistency
            saved_summary = self.get_reflection_summary_from_db(reflection_id, user_id)

            return UniversalResponse(
                success=True,
                reflection_id=str(reflection_id),
                sarthi_message="Your custom message has been saved. Ready to proceed.",
                current_stage=4,
                next_stage=100,
                progress=ProgressInfo(current_step=4, total_step=5, workflow_completed=False),
                data=[{
                    "summary": saved_summary,  # FROM DATABASE!
                    "edited": True,
                    "updated_at": reflection.updated_at.isoformat() if reflection.updated_at else None
                }]
            )

        elif edit_mode == "regenerate":
            history = get_buffer_memory(self.db, reflection_id, stage_no=4)
            system_prompt = self.get_system_prompt(reflection_id)
            
            # ASYNC LLM call
            flag, assistant_reply = await self.generate_llm_response(system_prompt, history, "regenerate summary")

            if assistant_reply and assistant_reply.startswith("{"):
                try:
                    summary_json = json.loads(assistant_reply)
                    if "user" in summary_json:
                        # 1. SAVE to database
                        reflection.reflection = summary_json["user"]
                        reflection.updated_at = datetime.utcnow()
                        self.db.commit()
                        
                        # 2. FETCH from database for consistency
                        saved_summary = self.get_reflection_summary_from_db(reflection_id, user_id)

                        return UniversalResponse(
                            success=True,
                            reflection_id=str(reflection_id),
                            sarthi_message="Here's a regenerated version of your message. You can still edit it if needed.",
                            current_stage=4,
                            next_stage=100,
                            progress=ProgressInfo(current_step=4, total_step=5, workflow_completed=False),
                            data=[{
                                "summary": saved_summary,  # FROM DATABASE!
                                "regenerated": True,
                                "updated_at": reflection.updated_at.isoformat() if reflection.updated_at else None
                            }]
                        )
                except json.JSONDecodeError:
                    raise HTTPException(status_code=500, detail="Failed to regenerate summary")

            raise HTTPException(status_code=500, detail="Regeneration failed")
        
        raise HTTPException(status_code=400, detail="Invalid edit mode")

    async def process_normal_conversation(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Handle normal conversation flow - ALWAYS fetch summary from DB"""
        reflection_id = uuid.UUID(request.reflection_id)
        user_message = request.message.strip()

        if not user_message:
            raise HTTPException(status_code=400, detail="Message is required for conversation")

        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found or access denied")

        history = get_buffer_memory(self.db, reflection_id, stage_no=4)
        turn_count = len([m for m in history if m["role"] == "user"])

        # Check turn limit
        if turn_count >= 6:
            raise HTTPException(status_code=400, detail="Conversation limit reached")

        # Check if conversation already completed
        if any("__DONE__" in msg["content"] for msg in history if msg["role"] == "assistant"):
            raise HTTPException(status_code=400, detail="Conversation already marked complete")

        # ASYNC LLM response generation
        system_prompt = self.get_system_prompt(reflection_id)
        flag, assistant_reply = await self.generate_llm_response(
            system_prompt, 
            history, 
            user_message
        )
        
        is_done = flag == "__DONE__" or turn_count >= 5  # Complete after 6 user messages

        # Store user message in database
        self.db.add(Message(
            text=user_message,
            reflection_id=reflection_id,
            sender=1,  # 1 = user
            stage_no=4
        ))

        # Initialize response variables
        sarthi_message = ""
        response_data = []
        
        # Handle conversation completion and summary generation
        if is_done and assistant_reply and assistant_reply.startswith("{"):
            try:
                summary_json = json.loads(assistant_reply)
                summary_text = summary_json.get("user")

                if summary_text and isinstance(summary_text, str):
                    # 1. SAVE summary to database
                    reflection.reflection = summary_text
                    reflection.updated_at = datetime.utcnow()
                    self.db.commit()

                    # 2. FETCH summary from database for consistency
                    saved_summary = self.get_reflection_summary_from_db(reflection_id, user_id)

                    # Set completion message (minimal as you prefer)
                    sarthi_message = "Perfect! Your reflection is ready."
                    response_data = [{
                        "summary": saved_summary,  # FROM DATABASE!
                        "conversation_complete": True,
                        "updated_at": reflection.updated_at.isoformat() if reflection.updated_at else None
                    }]
                else:
                    # JSON without valid user summary - treat as normal assistant reply
                    sarthi_message = assistant_reply
                    is_done = False
            except json.JSONDecodeError:
                # Not valid JSON - treat as normal assistant reply
                sarthi_message = assistant_reply
                is_done = False

        elif assistant_reply:
            # Normal assistant message (conversation continues)
            self.db.add(Message(
                text=assistant_reply,
                reflection_id=reflection_id,
                sender=0,  # 0 = assistant
                stage_no=4
            ))
            sarthi_message = assistant_reply
        else:
            # Fallback message
            sarthi_message = "Please continue sharing your thoughts."

        # ALWAYS check if summary exists (from any previous completion)
        existing_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
        if existing_summary and not is_done:  # Show existing summary if available
            response_data = [{
                "summary": existing_summary,  # FROM DATABASE!
                "conversation_in_progress": True
            }]

        self.db.commit()

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=sarthi_message,  # Always has a value
            current_stage=4,
            next_stage=100 if is_done else 4,
            progress=ProgressInfo(
                current_step=4,
                total_step=5,
                workflow_completed=is_done
            ),
            data=response_data  # Always a list, summary FROM DATABASE
        )

    async def process(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Main processing method - routes to appropriate handler"""
        # Validate inputs
        if not request.reflection_id:
            raise HTTPException(status_code=400, detail="Reflection ID is required for Stage 4")

        # Check for edit mode
        edit_mode = next((item.get("edit_mode") for item in request.data if "edit_mode" in item), None)
        
        if edit_mode in ["edit", "regenerate"]:
            return await self.process_edit_mode(request, user_id)
        else:
            return await self.process_normal_conversation(request, user_id)

    async def close(self):
        """Close async OpenAI client"""
        await self.openai_client.close()