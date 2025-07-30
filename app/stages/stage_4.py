from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, Message, CategoryDict
from fastapi import HTTPException
from app.memory import get_buffer_memory
import uuid
from openai import OpenAI
import json
import os
from datetime import datetime

class Stage4(BaseStage):
    """
    Stage 4: Guided conversation with LLM (6-turn limit) with automatic summary generation
    
    Features:
    - Plain text format: All user messages sent as plain text (consistent with history)
    - Backend message: User input count sent as separate system message
    - Turn limit management: Enforces 6-turn conversation limit
    
    Message Format:
    - User messages: Plain text (consistent with history)
    - Backend message: Separate system message with just the number
    
    Example:
    User says "hi" (3rd message) → LLM receives:
    {"role": "user", "content": "hi"}
    {"role": "system", "content": "3"}  // Backend message with count
    """

    def __init__(self, db):
        super().__init__(db)
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def get_stage_number(self) -> int:
        return 4

    def get_prompt(self) -> str:
        return "This method is not used in Stage4."

    def get_system_prompt(self, reflection_id: uuid.UUID) -> str:
        """
        Get system prompt from CategoryDict table based on reflection's category
        
        Args:
            reflection_id: The reflection ID
            
        Returns:
            System prompt string from database
        """
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
        """
        Simple count of user messages in the conversation
        
        Args:
            history: Conversation history
            
        Returns:
            Number of user inputs + 1 (for current message)
        """
        return len([msg for msg in history if msg["role"] == "user"]) + 1

    def generate_llm_response(self, system_prompt: str, history: list, user_input: str, backend_message: str = None) -> tuple[str, str | None]:
        """
        Generate LLM response with user message as plain text and backend message separately
        
        Args:
            system_prompt: System prompt for the conversation
            history: Conversation history
            user_input: User's message
            backend_message: Not used - only count is sent
        """
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
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            raw_reply = response.choices[0].message.content.strip()

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

    def process(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """
        Main processing method for Stage 4 conversations
        
        Args:
            request: Universal request object
            user_id: User ID
            
        Returns:
            Universal response object
        """
        reflection_id = uuid.UUID(request.reflection_id)
        user_message = request.message.strip()

        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found or access denied")

        edit_mode = next((item.get("edit_mode") for item in request.data if "edit_mode" in item), None)

        if edit_mode == "edit":
            from distress_detection import DistressDetector
            distress = DistressDetector().check(user_message)

            if distress == 1:
                raise HTTPException(status_code=400, detail="Distress detected in custom message")

            reflection.reflection = user_message
            reflection.stage_no = 4
            reflection.updated_at = datetime.utcnow()
            self.db.commit()

            return UniversalResponse(
                success=True,
                reflection_id=str(reflection_id),
                sarthi_message="Your custom message has been saved. Ready to proceed.",
                current_stage=4,
                next_stage=100,
                progress=ProgressInfo(current_step=4, total_step=5, workflow_completed=False),
                data=[]
            )

        elif edit_mode == "regenerate":
            history = get_buffer_memory(self.db, reflection_id, stage_no=4)
            system_prompt = self.get_system_prompt(reflection_id)
            flag, assistant_reply = self.generate_llm_response(system_prompt, history, "regenerate summary")

            if assistant_reply and assistant_reply.startswith("{"):
                try:
                    summary_json = json.loads(assistant_reply)
                    if "user" in summary_json:
                        reflection.reflection = summary_json["user"]
                        reflection.updated_at = datetime.utcnow()
                        self.db.commit()
                        
                        self.db.refresh(reflection)
                        full_updated_summary = reflection.reflection

                        return UniversalResponse(
                            success=True,
                            reflection_id=str(reflection_id),
                            sarthi_message="Here's a regenerated version of your message. You can still edit it if needed.",
                            current_stage=4,
                            next_stage=100,
                            progress=ProgressInfo(current_step=4, total_step=5, workflow_completed=False),
                            data=[{
                                "summary": full_updated_summary,
                                "regenerated": True,
                                "updated_at": reflection.updated_at.isoformat() if reflection.updated_at else None
                            }]
                        )
                except json.JSONDecodeError:
                    raise HTTPException(status_code=500, detail="Failed to regenerate summary")

            raise HTTPException(status_code=500, detail="Regeneration failed")

        history = get_buffer_memory(self.db, reflection_id, stage_no=4)
        turn_count = len([m for m in history if m["role"] == "user"])

        # Check turn limit
        if turn_count >= 6:
            raise HTTPException(status_code=400, detail="Conversation limit reached")

        # Check if conversation already completed
        if any("__DONE__" in msg["content"] for msg in history if msg["role"] == "assistant"):
            raise HTTPException(status_code=400, detail="Conversation already marked complete")

        # Generate LLM response with backend message (user count)
        system_prompt = self.get_system_prompt(reflection_id)
        flag, assistant_reply = self.generate_llm_response(
            system_prompt, 
            history, 
            user_message
        )
        
        is_done = flag == "__DONE__" or turn_count >= 10

        # Store user message in database
        self.db.add(Message(
            text=user_message,
            reflection_id=reflection_id,
            sender=1,  # 1 = user
            stage_no=4
        ))

        summary_data = None
        
        # Handle conversation completion and summary generation
        if is_done and assistant_reply and assistant_reply.startswith("{"):
            try:
                summary_json = json.loads(assistant_reply)
                if "user" in summary_json:
                    reflection.reflection = summary_json["user"]
                    reflection.updated_at = datetime.utcnow()
                    self.db.commit()
                    
                    summary_text = summary_json["user"]
                    
                    summary_data = {
                        "summary": summary_text
                    }
                    sarthi_response = (
                "Thanks for sharing all that. I've got everything I need — let's shape your message next. 💬"
            )
                else:
                    sarthi_response = assistant_reply
            except json.JSONDecodeError:
                sarthi_response = assistant_reply
        elif assistant_reply:
            # Store AI response in database
            self.db.add(Message(
                text=assistant_reply,
                reflection_id=reflection_id,
                sender=0,  # 0 = assistant
                stage_no=4
            ))
            sarthi_response = assistant_reply
        else:
            sarthi_response = "Please continue sharing your thoughts."

        self.db.commit()

        response_data = []
        if summary_data:
            response_data = [summary_data]

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=sarthi_response,
            current_stage=4,
            next_stage=100 if is_done else 4,
            progress=ProgressInfo(
                current_step=4,
                total_step=5,
                workflow_completed=False
            ),
            data=response_data
        )