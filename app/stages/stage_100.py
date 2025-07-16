from app.schemas import ProgressInfo, UniversalRequest, UniversalResponse
from app.database import SessionLocal
from app.models import Reflection, User  # Add User import
from sqlalchemy import update, select 
from services.email_service import send_email_message
from services.whatsapp_service import send_whatsapp_message

class Stage100:
    def __init__(self, db):
        self.db = db

    def handle(self, request: UniversalRequest, user_id: str) -> UniversalResponse:
        reflection_id = request.reflection_id
        if not reflection_id:
            raise ValueError("Reflection ID is required for Stage 100")

        delivery_mode = next((item.get("delivery_mode") for item in request.data if "delivery_mode" in item), None)

        if delivery_mode is None:
            raise ValueError("delivery_mode must be provided in request.data")

        # Fetch reflection and summary
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()

        if not reflection:
            raise ValueError("Reflection not found")

        # Get user info for email
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError("User not found")

        summary = reflection.reflection

        # Update stage_no and delivery_mode
        reflection.stage_no = 100
        reflection.delivery_mode = delivery_mode
        self.db.commit()

        # Send based on delivery mode
        if delivery_mode == 0:
            # Send email
            send_email_message(
                to_email=user.email,
                subject="Your Sarthi Reflection Summary",
                message=summary,
                is_html=False,
                recipient_name=user.name or "User"
            )
        elif delivery_mode == 1:
            # Send WhatsApp
            send_whatsapp_message(reflection_id, summary)
        elif delivery_mode == 2:
            # Send both email and WhatsApp
            send_email_message(
                to_email=user.email,
                subject="Your Sarthi Reflection Summary",
                message=summary,
                is_html=False,
                recipient_name=user.name or "User"
            )
            send_whatsapp_message(reflection_id, summary)
        elif delivery_mode == 3:
            pass  # Private — do nothing

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message="Your message is saved and delivery preferences have been recorded.",
            current_stage=100,
            next_stage=101,
            progress=ProgressInfo(current_step=5, total_step=5, workflow_completed=True),
            data=[]
        )