# app/stages/stage_100.py - COMPLETE UPDATED CODE

from app.schemas import ProgressInfo, UniversalRequest, UniversalResponse
from app.database import SessionLocal
from app.models import Reflection, User  # Add User import
from sqlalchemy import update, select 
from services.providers.email import EmailProvider
from services.providers.whatsapp import WhatsAppProvider

class Stage100:
    def __init__(self, db):
        self.db = db
        self.email_provider = EmailProvider()
        self.whatsapp_provider = WhatsAppProvider()

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
            metadata = {
                "subject": "Your Sarthi Reflection Summary",
                "recipient_name": user.name or "User"
            }
            self.email_provider.send(user.email, summary, metadata)
            
        elif delivery_mode == 1:
            # Send WhatsApp
            if user.phone_number:
                self.whatsapp_provider.send(str(user.phone_number), summary)
                
        elif delivery_mode == 2:
            # Send both email and WhatsApp
            metadata = {
                "subject": "Your Sarthi Reflection Summary",
                "recipient_name": user.name or "User"
            }
            self.email_provider.send(user.email, summary, metadata)
            
            if user.phone_number:
                self.whatsapp_provider.send(str(user.phone_number), summary)
                
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