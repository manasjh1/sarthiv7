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

            # Check for feedback email first (this bypasses everything)
            email_recipient = next((item.get("email") for item in request.data if "email" in item), None)
            if email_recipient:
                return self._handle_feedback_email(reflection_id, user_id, email_recipient)

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

            # Extract user choices from request data
            reveal_choice = next((item.get("reveal_name") for item in request.data if "reveal_name" in item), None)
            provided_name = next((item.get("name") for item in request.data if "name" in item), None)
            delivery_mode = next((item.get("delivery_mode") for item in request.data if "delivery_mode" in item), None)

            # ========== PHASE 1: IDENTITY REVEAL LOGIC (HAPPENS FIRST) ==========
            
            # Check if identity has been decided yet
            identity_decided = False
            
            if user.is_anonymous is True:
                # User chose to be anonymous during onboarding - auto-decide
                print(f"User {user_id} is anonymous from onboarding, auto-setting anonymous")
                reflection.is_anonymous = True
                reflection.sender_name = None
                identity_decided = True
                
            elif reveal_choice is not None:
                # User has made an identity choice for this reflection
                if reveal_choice is False:
                    reflection.is_anonymous = True
                    reflection.sender_name = None
                    print(f"User {user_id} chose to be anonymous for reflection {reflection_id}")
                    identity_decided = True
                    
                elif reveal_choice is True and provided_name is not None:
                    reflection.is_anonymous = False
                    reflection.sender_name = provided_name.strip()
                    print(f"User {user_id} chose to reveal name '{provided_name}' for reflection {reflection_id}")
                    identity_decided = True
                    
                elif reveal_choice is True and provided_name is None:
                    # User wants to reveal but hasn't provided name yet
                    default_name = user.name if user.name else ""
                    return UniversalResponse(
                        success=True,
                        reflection_id=str(reflection_id),
                        sarthi_message="Please enter your name to include it in your reflection.",
                        current_stage=100,
                        next_stage=100,
                        progress=ProgressInfo(current_step=5, total_step=5, workflow_completed=False),
                        data=[{
                            "input": {
                                "name": "name", 
                                "placeholder": "Enter your name",
                                "default_value": default_name
                            }
                        }]
                    )
            
            # If identity not decided yet, ask for it
            if not identity_decided:
                return UniversalResponse(
                    success=True,
                    reflection_id=str(reflection_id),
                    sarthi_message="Would you like to reveal your name in this message, or send it anonymously?",
                    current_stage=100,
                    next_stage=100,
                    progress=ProgressInfo(current_step=5, total_step=5, workflow_completed=False),
                    data=[{
                        "options": [
                            {"reveal_name": True, "label": "Reveal my name"},
                            {"reveal_name": False, "label": "Send anonymously"}
                        ]
                    }]
                )

            # ========== PHASE 2: DELIVERY MODE SELECTION ==========
            
            # Identity is decided, now check delivery mode
            if delivery_mode is None:
                # Show delivery options now that identity is decided
                return UniversalResponse(
                    success=True,
                    reflection_id=str(reflection_id),
                    sarthi_message="Perfect! How would you like to deliver your message?",
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
                        },
                        "identity_status": {
                            "is_anonymous": reflection.is_anonymous,
                            "sender_name": reflection.sender_name
                        }
                    }]
                )

            # ========== PHASE 3: FINAL DELIVERY ==========
            
            # Both identity and delivery mode are decided - process delivery
            if delivery_mode not in [0, 1, 2, 3]:
                raise HTTPException(status_code=400, detail="Invalid delivery mode")

            # Update and commit all changes
            reflection.delivery_mode = delivery_mode
            self.db.commit()

            # Handle actual delivery
            delivery_result = self._handle_delivery(delivery_mode, user, reflection.reflection)
            
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
                    "summary": reflection.reflection,
                    "is_anonymous": reflection.is_anonymous,
                    "recipient_name": reflection.name,      # Person reflection is about
                    "sender_name": reflection.sender_name   # Person sending the reflection
                }]
            )

        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid data: {str(e)}")
        except Exception as e:
            print(f"Stage 100 error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Stage 100 processing failed: {str(e)}")

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

            # Get sender name based on current reflection settings or user settings
            if hasattr(reflection, 'is_anonymous') and reflection.is_anonymous:
                sender_name = "Anonymous"
            elif hasattr(reflection, 'sender_name') and reflection.sender_name:
                sender_name = reflection.sender_name
            elif user.name:
                sender_name = user.name
            else:
                sender_name = "Anonymous"

            # Use AuthManager to send feedback email
            result = self.auth_manager.send_feedback_email(
                sender_name=sender_name,
                receiver_name=reflection.name or "Recipient",  # Person reflection is about
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
                    "sender": sender_name,
                    "about": reflection.name,  # Person reflection is about
                    "summary": reflection.reflection
                }]
            )

        except Exception as e:
            print(f"Feedback email sending failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to send feedback email: {str(e)}")

    def _return_delivery_options(self, reflection_id: uuid.UUID) -> UniversalResponse:
        """Return delivery options when no delivery_mode is provided - NOT USED IN NEW FLOW"""
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

    def _handle_delivery(self, delivery_mode: int, user: User, summary: str) -> dict:
        """Handle message delivery based on selected mode"""
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