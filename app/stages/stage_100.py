from app.schemas import ProgressInfo, UniversalRequest, UniversalResponse
from app.database import SessionLocal
from app.models import Reflection, User, Feedback
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
            
            if isinstance(user_id, str):
                user_id = uuid.UUID(user_id)

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

            # ========== PHASE 3: FEEDBACK COLLECTION (After Delivery) ==========
            
            # Check if this is a feedback submission
            feedback_choice = next((item.get("feedback") for item in request.data if "feedback" in item), None)
            
            # If delivery is complete and this is feedback request
            if (reflection.delivery_mode is not None and 
                reflection.delivery_mode >= 0 and 
                feedback_choice is not None):
                return self._handle_feedback_submission(reflection_id, reflection, feedback_choice)
            
            # If delivery is complete but no feedback yet, show feedback options
            if (reflection.delivery_mode is not None and 
                reflection.delivery_mode >= 0 and 
                (reflection.feedback_type is None or reflection.feedback_type == 0)):
                return self._show_feedback_options(reflection_id)
            
            # If feedback already submitted, show completion
            if reflection.feedback_type and reflection.feedback_type > 0:
                return self._show_feedback_already_submitted(reflection_id, reflection.feedback_type)

            # ========== PHASE 1 & 2: IDENTITY REVEAL AND DELIVERY ==========

            # Check for THIRD-PARTY email delivery (sending reflection TO someone else)
            third_party_email = next((item.get("email") for item in request.data if "email" in item), None)
            if third_party_email:
                return self._handle_third_party_email_delivery(reflection_id, user_id, third_party_email)

            # Extract user choices from request data
            reveal_choice = next((item.get("reveal_name") for item in request.data if "reveal_name" in item), None)
            provided_name = next((item.get("name") for item in request.data if "name" in item), None)
            delivery_mode = next((item.get("delivery_mode") for item in request.data if "delivery_mode" in item), None)

            # ========== PHASE 1: IDENTITY REVEAL LOGIC ==========
            
            identity_decided = False
            
            if user.is_anonymous is True:
                print(f"User {user_id} is anonymous from onboarding, auto-setting anonymous")
                reflection.is_anonymous = True
                reflection.sender_name = None
                identity_decided = True
                
            elif reveal_choice is not None:
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
                    default_name = user.name if user.name else ""
                    return UniversalResponse(
                        success=True,
                        reflection_id=str(reflection_id),
                        sarthi_message="Please enter your name to include it in your reflection.",
                        current_stage=100,
                        next_stage=100,
                        progress=ProgressInfo(current_step=5, total_step=6, workflow_completed=False),
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
                    progress=ProgressInfo(current_step=5, total_step=6, workflow_completed=False),
                    data=[{
                        "options": [
                            {"reveal_name": True, "label": "Reveal my name"},
                            {"reveal_name": False, "label": "Send anonymously"}
                        ]
                    }]
                )

            # ========== PHASE 2: DELIVERY MODE SELECTION ==========
            
            if delivery_mode is None:
                return UniversalResponse(
                    success=True,
                    reflection_id=str(reflection_id),
                    sarthi_message="Perfect! How would you like to deliver your message?",
                    current_stage=100,
                    next_stage=100,
                    progress=ProgressInfo(current_step=5, total_step=6, workflow_completed=False),
                    data=[{
                        "delivery_options": [
                            {"mode": 0, "name": "Email", "description": "Send via email"},
                            {"mode": 1, "name": "WhatsApp", "description": "Send via WhatsApp"},
                            {"mode": 2, "name": "Both", "description": "Send via both email and WhatsApp"},
                            {"mode": 3, "name": "Private", "description": "Keep it private (no delivery)"}
                        ],
                        "third_party_option": {
                            "description": "Or send to someone else's email",
                            "instruction": "Provide email in data like: {'email': 'recipient@example.com'}"
                        },
                        "identity_status": {
                            "is_anonymous": reflection.is_anonymous,
                            "sender_name": reflection.sender_name
                        }
                    }]
                )

            # ========== DELIVERY AND TRANSITION TO FEEDBACK ==========
            
            if delivery_mode not in [0, 1, 2, 3]:
                raise HTTPException(status_code=400, detail="Invalid delivery mode")

            # Update reflection with delivery info (DON'T change stage_no)
            reflection.delivery_mode = delivery_mode
            self.db.commit()

            # Handle actual delivery
            delivery_result = self._handle_standard_delivery(delivery_mode, user, reflection.reflection)
            
            # After delivery, show feedback options
            return self._show_feedback_options_after_delivery(reflection_id, delivery_result)

        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid data: {str(e)}")
        except Exception as e:
            print(f"Stage 100 error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Stage 100 processing failed: {str(e)}")

    def _handle_third_party_email_delivery(self, reflection_id: uuid.UUID, user_id: uuid.UUID, recipient_email: str) -> UniversalResponse:
        """Handle sending reflection TO someone else's email (third-party delivery)"""
        try:
            reflection = self.db.query(Reflection).filter(
                Reflection.reflection_id == reflection_id,
                Reflection.giver_user_id == user_id
            ).first()

            if not reflection:
                raise HTTPException(status_code=404, detail="Reflection not found or access denied")

            user = self.db.query(User).filter(User.user_id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Get sender name
            if hasattr(reflection, 'is_anonymous') and reflection.is_anonymous:
                sender_name = "Anonymous"
            elif hasattr(reflection, 'sender_name') and reflection.sender_name:
                sender_name = reflection.sender_name
            elif user.name:
                sender_name = user.name
            else:
                sender_name = "Anonymous"

            # Send reflection to third party email
            result = self.auth_manager.send_feedback_email(
                sender_name=sender_name,
                receiver_name=reflection.name or "Recipient",
                receiver_email=recipient_email,
                feedback_summary=reflection.reflection
            )

            if not result.success:
                raise HTTPException(status_code=500, detail=result.message)

            # Mark as delivered (set delivery_mode to indicate third-party email)
            reflection.delivery_mode = 4  # Or use existing mode + flag
            self.db.commit()

            # After third-party delivery, show feedback options
            return self._show_feedback_options_after_third_party_delivery(reflection_id, recipient_email, sender_name, reflection.name)

        except Exception as e:
            print(f"Third-party email delivery failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to send to third party: {str(e)}")

    def _handle_standard_delivery(self, delivery_mode: int, user: User, summary: str) -> dict:
        """Handle standard delivery modes (email to user, WhatsApp, private)"""
        delivery_status = []
        
        try:
            if delivery_mode == 0:  # Email to user
                if not user.email:
                    raise HTTPException(status_code=400, detail="User email not available")
                
                metadata = {
                    "subject": "Your Sarthi Reflection Summary",
                    "recipient_name": user.name or "User"
                }
                self.email_provider.send(user.email, summary, metadata)
                delivery_status.append("email_sent")
                message = "Your message has been sent via email successfully! 📧"
                
            elif delivery_mode == 1:  # WhatsApp
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

    def _show_feedback_options_after_delivery(self, reflection_id: uuid.UUID, delivery_result: dict) -> UniversalResponse:
        """Show feedback options after successful delivery"""
        
        # Fetch all feedback options from database (excluding 0 which is "pending")
        feedback_options = self.db.query(Feedback).filter(
            Feedback.feedback_no.between(1, 5)
        ).order_by(Feedback.feedback_no).all()

        if not feedback_options:
            raise HTTPException(status_code=500, detail="No feedback options found in database")

        # Format feedback options for response
        options_data = [
            {
                "feedback": option.feedback_no,
                "text": option.feedback_text
            }
            for option in feedback_options
        ]

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=f"{delivery_result['message']} Now, how are you feeling after completing this reflection?",
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=6, total_step=6, workflow_completed=False),
            data=[{
                "feedback_options": options_data,
                "instruction": "Select how you're feeling after this reflection experience",
                "delivery_status": delivery_result["status"]
            }]
        )

    def _show_feedback_options_after_third_party_delivery(self, reflection_id: uuid.UUID, recipient_email: str, sender_name: str, about_name: str) -> UniversalResponse:
        """Show feedback options after third-party email delivery"""
        
        # Fetch all feedback options from database
        feedback_options = self.db.query(Feedback).filter(
            Feedback.feedback_no.between(1, 5)
        ).order_by(Feedback.feedback_no).all()

        if not feedback_options:
            raise HTTPException(status_code=500, detail="No feedback options found in database")

        options_data = [
            {
                "feedback": option.feedback_no,
                "text": option.feedback_text
            }
            for option in feedback_options
        ]

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=f"Your reflection has been sent to {recipient_email} successfully! 📧 Now, how are you feeling after completing this reflection?",
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=6, total_step=6, workflow_completed=False),
            data=[{
                "feedback_options": options_data,
                "instruction": "Select how you're feeling after this reflection experience",
                "third_party_email_sent": True,
                "recipient": recipient_email,
                "sender": sender_name,
                "about": about_name
            }]
        )

    def _show_feedback_options(self, reflection_id: uuid.UUID) -> UniversalResponse:
        """Show feedback options when called directly (delivery already complete)"""
        
        feedback_options = self.db.query(Feedback).filter(
            Feedback.feedback_no.between(1, 5)
        ).order_by(Feedback.feedback_no).all()

        if not feedback_options:
            raise HTTPException(status_code=500, detail="No feedback options found in database")

        options_data = [
            {
                "feedback": option.feedback_no,
                "text": option.feedback_text
            }
            for option in feedback_options
        ]

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message="How are you feeling after completing this reflection? Your feedback helps us improve Sarthi for everyone.",
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=6, total_step=6, workflow_completed=False),
            data=[{
                "feedback_options": options_data,
                "instruction": "Select how you're feeling after this reflection experience"
            }]
        )

    def _handle_feedback_submission(self, reflection_id: uuid.UUID, reflection: Reflection, feedback_choice: int) -> UniversalResponse:
        """Handle feedback submission and complete workflow"""
        
        # Validate feedback choice
        if not isinstance(feedback_choice, int) or feedback_choice not in [1, 2, 3, 4, 5]:
            raise HTTPException(status_code=400, detail="Invalid feedback choice. Must be 1, 2, 3, 4, or 5")

        # Verify feedback option exists in database
        feedback_option = self.db.query(Feedback).filter(
            Feedback.feedback_no == feedback_choice
        ).first()

        if not feedback_option:
            raise HTTPException(status_code=400, detail=f"Feedback option {feedback_choice} not found in database")

        # Update reflection with feedback
        reflection.feedback_type = feedback_choice
        self.db.commit()

        # Return success response with feedback confirmation
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=f"Thank you for your feedback! You selected: '{feedback_option.feedback_text}'. Your journey with Sarthi is now complete. 🌟",
            current_stage=100,
            next_stage=101,  # Logical completion
            progress=ProgressInfo(current_step=6, total_step=6, workflow_completed=True),
            data=[{
                "feedback_submitted": True,
                "feedback_choice": feedback_choice,
                "feedback_text": feedback_option.feedback_text,
                "workflow_complete": True
            }]
        )

    def _show_feedback_already_submitted(self, reflection_id: uuid.UUID, feedback_type: int) -> UniversalResponse:
        """Show message when feedback has already been submitted"""
        
        # Get the feedback text
        feedback_option = self.db.query(Feedback).filter(
            Feedback.feedback_no == feedback_type
        ).first()
        
        feedback_text = feedback_option.feedback_text if feedback_option else f"Option {feedback_type}"

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=f"You have already submitted your feedback: '{feedback_text}'. Thank you for using Sarthi! 🌟",
            current_stage=100,
            next_stage=101,
            progress=ProgressInfo(current_step=6, total_step=6, workflow_completed=True),
            data=[{
                "feedback_already_submitted": True,
                "feedback_choice": feedback_type,
                "feedback_text": feedback_text,
                "workflow_complete": True
            }]
        )