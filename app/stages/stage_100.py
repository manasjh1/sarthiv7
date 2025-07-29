from app.schemas import ProgressInfo, UniversalRequest, UniversalResponse
from app.database import SessionLocal
from app.models import Reflection, User
from sqlalchemy import update, select 
from services.providers.email import EmailProvider
from services.providers.whatsapp import WhatsAppProvider
from services.auth.manager import AuthManager  
from fastapi import HTTPException
import uuid


class Stage100:
    def __init__(self, db):
        self.db = db
        self.email_provider = EmailProvider()
        self.whatsapp_provider = WhatsAppProvider()
        self.auth_manager = AuthManager()  

    def handle(self, request: UniversalRequest, user_id: str) -> UniversalResponse:
        try:
            reflection_id = request.reflection_id
            if not reflection_id:
                raise HTTPException(status_code=400, detail="Reflection ID is required for Stage 100")

            # Convert string to UUID if needed
            if isinstance(reflection_id, str):
                reflection_id = uuid.UUID(reflection_id)
            
            # Convert user_id to UUID if needed
            if isinstance(user_id, str):
                user_id = uuid.UUID(user_id)

            # NEW: Check for email in data
            email_recipient = next((item.get("email") for item in request.data if "email" in item), None)
            
            if email_recipient:
                return self._handle_feedback_email(reflection_id, user_id, email_recipient)

            # EXISTING FUNCTIONALITY CONTINUES UNCHANGED
            delivery_mode = next((item.get("delivery_mode") for item in request.data if "delivery_mode" in item), None)

            # If no delivery_mode, return delivery options
            if delivery_mode is None:
                return self._return_delivery_options(reflection_id)

            # Fetch reflection and summary
            reflection = self.db.query(Reflection).filter(
                Reflection.reflection_id == reflection_id,
                Reflection.giver_user_id == user_id
            ).first()

            if not reflection:
                raise HTTPException(status_code=404, detail="Reflection not found or access denied")

            # Check if summary exists
            if not reflection.reflection or not reflection.reflection.strip():
                raise HTTPException(status_code=400, detail="No summary available for delivery")

            # Get user info for delivery
            user = self.db.query(User).filter(User.user_id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            summary = reflection.reflection

            # Validate delivery_mode
            if delivery_mode not in [0, 1, 2, 3]:
                raise HTTPException(status_code=400, detail="Invalid delivery mode")

            # Update delivery_mode (keep stage_no as 100)
            reflection.delivery_mode = delivery_mode
            self.db.commit()

            # Handle delivery based on mode
            delivery_result = self._handle_delivery(delivery_mode, user, summary)
            
            return UniversalResponse(
                success=True,
                reflection_id=str(reflection_id),
                sarthi_message=delivery_result["message"],
                current_stage=100,
                next_stage=101,
                progress=ProgressInfo(current_step=5, total_step=5, workflow_completed=True),
                data=[{
                    "delivery_status": delivery_result["status"],
                    "delivery_mode": delivery_mode,
                    "summary": summary
                }]
            )

        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid data: {str(e)}")
        except Exception as e:
            print(f"Stage 100 error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Stage 100 processing failed: {str(e)}")

    # NEW METHOD: Handle feedback email
    def _handle_feedback_email(self, reflection_id: uuid.UUID, user_id: uuid.UUID, email_recipient: str) -> UniversalResponse:
        """Handle sending feedback email using AuthManager"""
        try:
            # Fetch reflection and user data
            reflection = self.db.query(Reflection).filter(
                Reflection.reflection_id == reflection_id,
                Reflection.giver_user_id == user_id
            ).first()

            if not reflection:
                raise HTTPException(status_code=404, detail="Reflection not found or access denied")

            if not reflection.reflection or not reflection.reflection.strip():
                raise HTTPException(status_code=400, detail="No summary available for delivery")

            user = self.db.query(User).filter(User.user_id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Use AuthManager to send feedback email (same pattern as OTP)
            result = self.auth_manager.send_feedback_email(
                sender_name=user.name or "Anonymous",
                receiver_name=reflection.name or "Recipient", 
                receiver_email=email_recipient,
                feedback_summary=reflection.reflection
            )

            if not result.success:
                raise HTTPException(status_code=500, detail=result.message)

            return UniversalResponse(
                success=True,
                reflection_id=str(reflection_id),
                sarthi_message=f"Feedback email has been sent successfully to {email_recipient}! 📧",
                current_stage=100,
                next_stage=101,
                progress=ProgressInfo(current_step=5, total_step=5, workflow_completed=True),
                data=[{
                    "email_sent": True,
                    "recipient": email_recipient,
                    "sender": user.name or "Anonymous",
                    "summary": reflection.reflection
                }]
            )

        except Exception as e:
            print(f"Feedback email sending failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to send feedback email: {str(e)}")

    # UPDATED: Add feedback option to existing method
    def _return_delivery_options(self, reflection_id: uuid.UUID) -> UniversalResponse:
        """Return delivery options when no delivery_mode is provided"""
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message="Perfect! Your message is ready. How would you like to deliver it?",
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=5, total_step=5, workflow_completed=False),
            data=[{
                "delivery_options": [
                    {"mode": 0, "name": "Email", "description": "Send via email"},
                    {"mode": 1, "name": "WhatsApp", "description": "Send via WhatsApp"},
                    {"mode": 2, "name": "Both", "description": "Send via both email and WhatsApp"},
                    {"mode": 3, "name": "Private", "description": "Keep it private (no delivery)"}
                ],
                "feedback_option": {
                    "description": "Or send feedback to someone else",
                    "instruction": "Provide email in data like: {'email': 'recipient@example.com'}"
                }
            }]
        )

    # KEEP ALL EXISTING METHODS UNCHANGED
    def _handle_delivery(self, delivery_mode: int, user: User, summary: str) -> dict:
        """Handle message delivery based on selected mode (existing functionality)"""
        delivery_status = []
        
        try:
            if delivery_mode == 0:  # Email only
                if not user.email:
                    raise HTTPException(status_code=400, detail="User email not available")
                
                metadata = {
                    "subject": "Your Sarthi Reflection Summary",
                    "recipient_name": user.name or "User"
                }
                self.email_provider.send(user.email, summary, metadata)
                delivery_status.append("email_sent")
                message = "Your message has been sent via email successfully! 📧"
                
            elif delivery_mode == 1:  # WhatsApp only
                if not user.phone_number:
                    raise HTTPException(status_code=400, detail="User phone number not available")
                
                self.whatsapp_provider.send(str(user.phone_number), summary)
                delivery_status.append("whatsapp_sent")
                message = "Your message has been sent via WhatsApp successfully! 📱"
                
            elif delivery_mode == 2:  # Both email and WhatsApp
                sent_methods = []
                
                if user.email:
                    try:
                        metadata = {
                            "subject": "Your Sarthi Reflection Summary",
                            "recipient_name": user.name or "User"
                        }
                        self.email_provider.send(user.email, summary, metadata)
                        delivery_status.append("email_sent")
                        sent_methods.append("email")
                    except Exception as e:
                        print(f"Email sending failed: {str(e)}")
                
                if user.phone_number:
                    try:
                        self.whatsapp_provider.send(str(user.phone_number), summary)
                        delivery_status.append("whatsapp_sent")
                        sent_methods.append("WhatsApp")
                    except Exception as e:
                        print(f"WhatsApp sending failed: {str(e)}")
                
                if not sent_methods:
                    raise HTTPException(status_code=400, detail="Neither email nor phone number available")
                
                message = f"Your message has been sent via {' and '.join(sent_methods)} successfully! 📧📱"
                
            elif delivery_mode == 3:  # Private
                delivery_status.append("private")
                message = "Your message has been saved privately. No delivery was made. 🔒"
            
            return {
                "status": delivery_status,
                "message": message
            }
            
        except Exception as e:
            print(f"Delivery failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Message delivery failed: {str(e)}")