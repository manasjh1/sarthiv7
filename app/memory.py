from app.models import Message
import uuid
from sqlalchemy.orm import Session

def get_buffer_memory(db: Session, reflection_id: uuid.UUID, stage_no: int = 4) -> list:
    messages = db.query(Message).filter(
        Message.reflection_id == reflection_id,
        Message.stage_no == stage_no
    ).order_by(Message.created_at).all()

    return [
        {
            "role": "user" if m.sender == 1 else "assistant",
            "content": m.text
        }
        for m in messages
    ]
