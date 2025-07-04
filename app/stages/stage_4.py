from app.stages.base_stage import BaseStage
from app.schemas import UniversalRequest, UniversalResponse, ProgressInfo
from app.models import Reflection, Message, CategoryDict
from fastapi import HTTPException
from app.memory import get_buffer_memory
import uuid
import openai
import json


class Stage4(BaseStage):
    """Stage 4: Guided conversation with LLM (6-turn limit + __DONE__ flag) - NO distress detection here"""

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

            # Detect system flag like {"system_flag": "__DONE__"}
            if raw_reply.startswith("{") and "system_flag" in raw_reply:
                parsed = json.loads(raw_reply)
                if parsed.get("system_flag") == "__DONE__":
                    return "__DONE__", None

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

        # Prevent more than 6 user turns
        turn_count = len([m for m in history if m["role"] == "user"])
        if turn_count >= 6:
            raise HTTPException(status_code=400, detail="Conversation limit reached")

        # Prevent sending message if already ended
        if any("__DONE__" in msg["content"] for msg in history if msg["role"] == "assistant"):
            raise HTTPException(status_code=400, detail="Conversation already marked complete")

        system_prompt = self.get_system_prompt(reflection_id)

        # Generate LLM response (NOT checked for distress)
        flag, assistant_reply = self.generate_llm_response(system_prompt, history, user_message)

        is_done = flag == "__DONE__"

        # Save user message (is_distress flag already set by stage_handler)
        self.db.add(Message(
            text=user_message,
            reflection_id=reflection_id,
            sender=1,
            stage_no=4
            # is_distress field will be set by stage_handler
        ))

        # Save assistant reply (NOT checked for distress)
        if assistant_reply:
            self.db.add(Message(
                text=assistant_reply,
                reflection_id=reflection_id,
                sender=0,
                stage_no=4
            ))

        self.db.commit()

        # Friendly closing message if done (fallback for None)
        sarthi_response = assistant_reply or (
            "Thanks for sharing all that. I've got everything I need — let's shape your message next. 💬"
        )

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=sarthi_response,  
            current_stage=4,
            next_stage=4,
            progress=ProgressInfo(
                current_step=4,
                total_step=4,
                workflow_completed=is_done
            ),
            data=[]
        )