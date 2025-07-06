from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, Message, CategoryDict
from fastapi import HTTPException
from app.memory import get_buffer_memory
import uuid
import openai
import json


class Stage4(BaseStage):
    """Stage 4: Guided conversation with LLM (6-turn limit) with automatic summary generation"""

    def get_stage_number(self) -> int:
        return 4

    def get_prompt(self) -> str:
        # Required only for abstract base class
        return "This method is not used in Stage4."

    def get_system_prompt(self, reflection_id: uuid.UUID) -> str:
        # Fetch system prompt for current category
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

    def generate_llm_response(self, system_prompt: str, history: list, user_input: str) -> tuple[str, str | None]:
        # Pass system prompt + history + user input to LLM
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=messages
            )
            raw_reply = response["choices"][0]["message"]["content"].strip()

            # Check if the response contains the final JSON format (even within other text)
            if "{" in raw_reply and "\"user\":" in raw_reply:
                try:
                    # Extract JSON from the response (it might be mixed with other text)
                    start_idx = raw_reply.find("{")
                    end_idx = raw_reply.rfind("}") + 1
                    if start_idx != -1 and end_idx > start_idx:
                        json_part = raw_reply[start_idx:end_idx]
                        parsed = json.loads(json_part)
                        if "user" in parsed:  # This is the final summary JSON
                            return "__DONE__", json_part  # Return just the JSON part
                except (json.JSONDecodeError, ValueError):
                    pass

            # Detect system flag like {"system_flag": "__DONE__"}
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
        reflection_id = uuid.UUID(request.reflection_id)
        user_message = request.message.strip()

        if not user_message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()
        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found or access denied")

        # NO DISTRESS DETECTION HERE - handled by stage_handler before this method is called

        history = get_buffer_memory(self.db, reflection_id, stage_no=4)

        # Count user turns
        turn_count = len([m for m in history if m["role"] == "user"])

        # Prevent more than 6 user turns
        if turn_count >= 6:
            raise HTTPException(status_code=400, detail="Conversation limit reached")

        # Prevent sending message if already ended
        if any("__DONE__" in msg["content"] for msg in history if msg["role"] == "assistant"):
            raise HTTPException(status_code=400, detail="Conversation already marked complete")

        system_prompt = self.get_system_prompt(reflection_id)

        # Generate LLM response
        flag, assistant_reply = self.generate_llm_response(system_prompt, history, user_message)

        # Check if conversation should end (either LLM says __DONE__ or it's the 6th turn)
        is_done = flag == "__DONE__" or turn_count >= 5

        # Save user message (is_distress flag already set by stage_handler)
        self.db.add(Message(
            text=user_message,
            reflection_id=reflection_id,
            sender=1,
            stage_no=4
        ))

        # Handle final summary JSON response
        summary_data = None
        if is_done and assistant_reply and assistant_reply.startswith("{"):
            try:
                # Parse the JSON response from LLM
                summary_json = json.loads(assistant_reply)
                if "user" in summary_json:
                    # Save the final reflection to database
                    reflection.reflection = summary_json["user"]
                    self.db.commit()
                    
                    # Prepare summary data for frontend
                    summary_data = {
                        "summary": summary_json["user"]
                    }
                    
                    # Set thank you message
                    sarthi_response = "Thanks for sharing all that. I've got everything I need — let's shape your message next. 💬"
                else:
                    # Regular conversation continues
                    sarthi_response = assistant_reply
            except json.JSONDecodeError:
                # If JSON parsing fails, treat as regular response
                sarthi_response = assistant_reply
        elif assistant_reply:
            # Save regular assistant reply
            self.db.add(Message(
                text=assistant_reply,
                reflection_id=reflection_id,
                sender=0,
                stage_no=4
            ))
            sarthi_response = assistant_reply
        else:
            sarthi_response = "Please continue sharing your thoughts."

        self.db.commit()

        # Prepare response data
        response_data = []
        if summary_data:
            response_data = [summary_data]

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=sarthi_response,  
            current_stage=4,
            next_stage=5 if is_done else 4,
            progress=ProgressInfo(
                current_step=4,
                total_step=5,
                workflow_completed=False
            ),
            data=response_data
        )