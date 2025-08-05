from app.schemas import ProgressInfo, UniversalRequest, UniversalResponse
from app.database import SessionLocal
from app.models import Reflection, User, Feedback
from sqlalchemy import update, select 
from services.providers.email import EmailProvider
from services.providers.whatsapp import WhatsAppProvider
from services.auth.manager import AuthManager  
from fastapi import HTTPException
from typing import Dict, Any, Optional
import uuid
import logging


class Stage100:
    """
    Stage 100: Identity Reveal, Delivery Mode Selection, Message Delivery, and Feedback Collection
    FIXED: Always fetch summary from database for consistency
    """

    def __init__(self, db):
        """Initialize Stage 100 with required services"""
        self.db = db
        self.email_provider = EmailProvider()
        self.whatsapp_provider = WhatsAppProvider()
        self.auth_manager = AuthManager()
        self.logger = logging.getLogger(__name__)

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

    async def handle(self, request: UniversalRequest, user_id: str) -> UniversalResponse:
        """Main Stage 100 handler - ALWAYS fetch summary from database"""
        try:
            # Input validation and conversion
            reflection_id = self._validate_and_convert_reflection_id(request.reflection_id)
            user_uuid = self._validate_and_convert_user_id(user_id)

            # Fetch and validate reflection
            reflection = self._get_reflection(reflection_id, user_uuid)
            
            # ALWAYS fetch summary from database
            current_summary = self.get_reflection_summary_from_db(reflection_id, user_uuid)
            if not current_summary:
                raise HTTPException(
                    status_code=400, 
                    detail="No summary available for delivery. Please complete Stage 4 first."
                )

            # Fetch and validate user
            user = self._get_user(user_uuid)

            # Extract user choices from request
            choices = self._extract_user_choices(request.data)
            
            self.logger.info(f"Stage 100 processing for reflection {reflection_id} - Choices: {choices}")

            # ========== FEEDBACK PHASE (Final Phase) ==========
            if choices.get('feedback_choice') is not None:
                return self._handle_feedback_submission(reflection_id, user_uuid, choices['feedback_choice'])
            
            # If feedback already submitted, show completion
            if reflection.feedback_type and reflection.feedback_type > 0:
                return self._show_feedback_already_submitted(reflection_id, user_uuid, reflection.feedback_type)

            # ========== THIRD-PARTY EMAIL DELIVERY ==========
            if choices.get('third_party_email'):
                return await self._handle_third_party_email_delivery(
                    reflection_id, user_uuid, choices['third_party_email']
                )

            # ========== IDENTITY REVEAL PHASE ==========
            identity_status = self._get_identity_status(reflection, user, choices, reflection_id, user_uuid)
            
            if identity_status['needs_input']:
                return identity_status['response']

            # ========== DELIVERY MODE SELECTION ==========
            if choices.get('delivery_mode') is not None:
                return await self._handle_delivery_mode_selection(
                    reflection, user, choices['delivery_mode'], reflection_id, user_uuid
                )
            
            # If identity decided but delivery mode not selected, show delivery options
            if identity_status['decided'] and reflection.delivery_mode is None:
                return self._show_delivery_options(reflection_id, user_uuid)

            # ========== POST-DELIVERY FEEDBACK ==========
            # If delivery is complete, show feedback options
            if reflection.delivery_mode is not None:
                return self._show_feedback_options(reflection_id, user_uuid)
            
            # FIRST TIME ENTERING STAGE 100 - Show summary and identity options
            return self._show_stage100_initial_view(reflection_id, user_uuid)

        except HTTPException:
            raise
        except ValueError as e:
            self.logger.error(f"Validation error in Stage 100: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid data: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error in Stage 100: {str(e)}")
            raise HTTPException(status_code=500, detail="Stage 100 processing failed")

    def _show_stage100_initial_view(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> UniversalResponse:
        """Show initial Stage 100 view with summary from database"""
        # ALWAYS fetch from database
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message="Here's your reflection summary. Now, let's prepare to deliver your message. Would you like to reveal your name or send it anonymously?",
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=5, total_step=6, workflow_completed=False),
            data=[{
                "summary": current_summary,  # FROM DATABASE!
                "next_step": "identity_reveal",
                "options": [
                    {"reveal_name": True, "label": "Reveal my name"},
                    {"reveal_name": False, "label": "Send anonymously"}
                ]
            }]
        )

    def _validate_and_convert_reflection_id(self, reflection_id: Optional[str]) -> uuid.UUID:
        """Validate and convert reflection ID to UUID"""
        if not reflection_id:
            raise HTTPException(status_code=400, detail="Reflection ID is required for Stage 100")
        
        try:
            return uuid.UUID(reflection_id) if isinstance(reflection_id, str) else reflection_id
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid reflection ID format")

    def _validate_and_convert_user_id(self, user_id: str) -> uuid.UUID:
        """Validate and convert user ID to UUID"""
        try:
            return uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format")

    def _get_reflection(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> Reflection:
        """Get and validate reflection from database"""
        reflection = self.db.query(Reflection).filter(
            Reflection.reflection_id == reflection_id,
            Reflection.giver_user_id == user_id
        ).first()

        if not reflection:
            raise HTTPException(status_code=404, detail="Reflection not found or access denied")
        
        return reflection

    def _get_user(self, user_id: uuid.UUID) -> User:
        """Get and validate user from database"""
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    def _extract_user_choices(self, data: list) -> Dict[str, Any]:
        """Extract user choices from request data"""
        choices = {}
        
        for item in data:
            if isinstance(item, dict):
                # Extract various choice types
                if "feedback" in item:
                    choices['feedback_choice'] = item.get("feedback")
                if "email" in item:
                    choices['third_party_email'] = item.get("email")
                if "reveal_name" in item:
                    choices['reveal_choice'] = item.get("reveal_name")
                if "name" in item:
                    choices['provided_name'] = item.get("name")
                if "delivery_mode" in item:
                    choices['delivery_mode'] = item.get("delivery_mode")
        
        return choices

    def _get_identity_status(self, reflection: Reflection, user: User, choices: Dict[str, Any], reflection_id: uuid.UUID, user_id: uuid.UUID) -> Dict[str, Any]:
        """Determine identity reveal status and return appropriate response - ALWAYS fetch summary from DB"""
        # Check if identity has already been decided
        identity_decided = (
            hasattr(reflection, 'is_anonymous') and 
            reflection.is_anonymous is not None
        )
        
        # Auto-decide for anonymous users from onboarding
        if not identity_decided and user.is_anonymous is True:
            self.logger.info(f"Auto-setting anonymous for user {user.user_id}")
            reflection.is_anonymous = True
            reflection.sender_name = None
            self.db.commit()
            return {'decided': True, 'needs_input': False}
        
        # Process reveal choice from current request
        reveal_choice = choices.get('reveal_choice')
        provided_name = choices.get('provided_name')
        
        if not identity_decided and reveal_choice is not None:
            if reveal_choice is False:
                reflection.is_anonymous = True
                reflection.sender_name = None
                self.db.commit()
                self.logger.info(f"User chose anonymous for reflection {reflection.reflection_id}")
                return {'decided': True, 'needs_input': False}
                
            elif reveal_choice is True:
                if provided_name is not None:
                    reflection.is_anonymous = False
                    reflection.sender_name = provided_name.strip()
                    self.db.commit()
                    self.logger.info(f"User provided name '{provided_name}' for reflection {reflection.reflection_id}")
                    return {'decided': True, 'needs_input': False}
                else:
                    # Ask for name input - fetch summary from DB
                    current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
                    default_name = user.name if user.name else ""
                    
                    response = UniversalResponse(
                        success=True,
                        reflection_id=str(reflection.reflection_id),
                        sarthi_message="Please enter your name to include it in your reflection.",
                        current_stage=100,
                        next_stage=100,
                        progress=ProgressInfo(current_step=5, total_step=6, workflow_completed=False),
                        data=[{
                            "summary": current_summary,  # FROM DATABASE!
                            "input": {
                                "name": "name", 
                                "placeholder": "Enter your name",
                                "default_value": default_name
                            }
                        }]
                    )
                    return {'decided': False, 'needs_input': True, 'response': response}
        
        # Process provided name (when reveal_name was True in previous request)
        elif not identity_decided and provided_name is not None:
            reflection.is_anonymous = False
            reflection.sender_name = provided_name.strip()
            self.db.commit()
            self.logger.info(f"User provided name '{provided_name}' for reflection {reflection.reflection_id}")
            return {'decided': True, 'needs_input': False}
        
        # If identity still not decided, ask for it - fetch summary from DB
        if not identity_decided:
            current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
            
            response = UniversalResponse(
                success=True,
                reflection_id=str(reflection.reflection_id),
                sarthi_message="Here's your reflection summary. Would you like to reveal your name in this message, or send it anonymously?",
                current_stage=100,
                next_stage=100,
                progress=ProgressInfo(current_step=5, total_step=6, workflow_completed=False),
                data=[{
                    "summary": current_summary,  # FROM DATABASE!
                    "options": [
                        {"reveal_name": True, "label": "Reveal my name"},
                        {"reveal_name": False, "label": "Send anonymously"}
                    ]
                }]
            )
            return {'decided': False, 'needs_input': True, 'response': response}
        
        return {'decided': True, 'needs_input': False}

    def _show_delivery_options(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> UniversalResponse:
        """Show delivery mode options to user - fetch summary from DB"""
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
        reflection = self._get_reflection(reflection_id, user_id)
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message="Perfect! How would you like to deliver your message?",
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=5, total_step=6, workflow_completed=False),
            data=[{
                "summary": current_summary,  # FROM DATABASE!
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

    async def _handle_delivery_mode_selection(
        self, 
        reflection: Reflection, 
        user: User, 
        delivery_mode: int, 
        reflection_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> UniversalResponse:
        """Handle delivery mode selection and execute delivery"""
        
        # Validate delivery mode
        if delivery_mode not in [0, 1, 2, 3]:
            raise HTTPException(status_code=400, detail="Invalid delivery mode")

        # Update reflection with delivery mode
        reflection.delivery_mode = delivery_mode
        self.db.commit()
        
        # Get summary from database for delivery
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
        
        self.logger.info(f"Delivery mode {delivery_mode} selected for reflection {reflection_id}")

        # Handle actual delivery
        delivery_result = await self._handle_standard_delivery(delivery_mode, user, current_summary)
        
        # After successful delivery, show feedback options
        return self._show_feedback_options_after_delivery(reflection_id, user_id, delivery_result)

    async def _handle_standard_delivery(self, delivery_mode: int, user: User, summary: str) -> Dict[str, Any]:
        """Handle standard delivery modes with comprehensive error handling and logging"""
        delivery_status = []
        
        try:
            if delivery_mode == 0:  # Email only
                await self._deliver_via_email(user, summary, delivery_status)
                message = "Your message has been sent via email successfully! 📧"
                
            elif delivery_mode == 1:  # WhatsApp only
                await self._deliver_via_whatsapp(user, summary, delivery_status)
                message = "Your message has been sent via WhatsApp successfully! 📱"
                
            elif delivery_mode == 2:  # Both email and WhatsApp
                sent_methods = []
                await self._deliver_via_both(user, summary, delivery_status, sent_methods)
                
                if not sent_methods:
                    raise HTTPException(
                        status_code=400, 
                        detail="Neither email nor phone number available, or both delivery methods failed"
                    )
                
                message = f"Your message has been sent via {' and '.join(sent_methods)} successfully! 📧📱"
                
            elif delivery_mode == 3:  # Private
                delivery_status.append("private")
                message = "Your message has been saved privately. No delivery was made. 🔒"
                self.logger.info("Private mode selected - no actual delivery")
            
            self.logger.info(f"Delivery completed - Status: {delivery_status}, Message: {message}")
            
            return {
                "status": delivery_status,
                "message": message
            }
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Delivery failed with exception: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Message delivery failed: {str(e)}")

    async def _deliver_via_email(self, user: User, summary: str, delivery_status: list):
        """Deliver message via email"""
        if not user.email:
            raise HTTPException(status_code=400, detail="User email not available")
        
        self.logger.info(f"Attempting email delivery to {user.email}")
        
        metadata = {
            "subject": "Your Sarthi Reflection Summary",
            "recipient_name": user.name or "User"
        }
        
        result = await self.email_provider.send(user.email, summary, metadata)
        
        self.logger.info(f"Email result - Success: {result.success}, Error: {result.error if not result.success else 'None'}")
        
        if not result.success:
            raise HTTPException(status_code=500, detail=f"Email sending failed: {result.error}")
            
        delivery_status.append("email_sent")

    async def _deliver_via_whatsapp(self, user: User, summary: str, delivery_status: list):
        """Deliver message via WhatsApp"""
        if not user.phone_number:
            raise HTTPException(status_code=400, detail="User phone number not available")
        
        self.logger.info(f"Attempting WhatsApp delivery to {user.phone_number}")
        
        result = await self.whatsapp_provider.send(str(user.phone_number), summary)
        
        self.logger.info(f"WhatsApp result - Success: {result.success}, Error: {result.error if not result.success else 'None'}")
        
        if not result.success:
            raise HTTPException(status_code=500, detail=f"WhatsApp sending failed: {result.error}")
            
        delivery_status.append("whatsapp_sent")

    async def _deliver_via_both(self, user: User, summary: str, delivery_status: list, sent_methods: list):
        """Deliver message via both email and WhatsApp"""
        
        # Try email delivery
        if user.email:
            try:
                self.logger.info(f"Attempting email delivery to {user.email} (Both mode)")
                metadata = {
                    "subject": "Your Sarthi Reflection Summary",
                    "recipient_name": user.name or "User"
                }
                result = await self.email_provider.send(user.email, summary, metadata)
                if result.success:
                    delivery_status.append("email_sent")
                    sent_methods.append("email")
                    self.logger.info("Email sent successfully in Both mode")
                else:
                    self.logger.warning(f"Email failed in Both mode: {result.error}")
            except Exception as e:
                self.logger.warning(f"Email exception in Both mode: {str(e)}")

        # Try WhatsApp delivery
        if user.phone_number:
            try:
                self.logger.info(f"Attempting WhatsApp delivery to {user.phone_number} (Both mode)")
                result = await self.whatsapp_provider.send(str(user.phone_number), summary)
                if result.success:
                    delivery_status.append("whatsapp_sent")
                    sent_methods.append("WhatsApp")
                    self.logger.info("WhatsApp sent successfully in Both mode")
                else:
                    self.logger.warning(f"WhatsApp failed in Both mode: {result.error}")
            except Exception as e:
                self.logger.warning(f"WhatsApp exception in Both mode: {str(e)}")

    async def _handle_third_party_email_delivery(
        self, 
        reflection_id: uuid.UUID, 
        user_id: uuid.UUID, 
        recipient_email: str
    ) -> UniversalResponse:
        """Handle sending reflection to someone else's email (third-party delivery)"""
        
        try:
            # Validate email format
            if not self._is_valid_email(recipient_email):
                raise HTTPException(status_code=400, detail="Invalid email address format")

            reflection = self._get_reflection(reflection_id, user_id)
            user = self._get_user(user_id)

            # Get sender name and summary from database
            sender_name = self._get_sender_name(reflection, user)
            current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)

            self.logger.info(f"Attempting third-party email delivery to {recipient_email}")

            # Send reflection via third-party email
            result = await self.auth_manager.send_feedback_email(
                sender_name=sender_name,
                receiver_name=reflection.name or "Recipient",
                receiver_email=recipient_email,
                feedback_summary=current_summary
            )

            if not result.success:
                raise HTTPException(status_code=500, detail=result.message)

            # Mark as delivered with third-party flag
            reflection.delivery_mode = 4  # Special mode for third-party email
            self.db.commit()

            return self._show_feedback_options_after_third_party_delivery(
                reflection_id, user_id, recipient_email, sender_name, reflection.name
            )

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Third-party email delivery failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to send to third party: {str(e)}")

    def _is_valid_email(self, email: str) -> bool:
        """Validate email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email.strip()) is not None

    def _get_sender_name(self, reflection: Reflection, user: User) -> str:
        """Get appropriate sender name based on anonymity settings"""
        if hasattr(reflection, 'is_anonymous') and reflection.is_anonymous:
            return "Anonymous"
        elif hasattr(reflection, 'sender_name') and reflection.sender_name:
            return reflection.sender_name
        elif user.name:
            return user.name
        else:
            return "Anonymous"

    def _show_feedback_options_after_delivery(self, reflection_id: uuid.UUID, user_id: uuid.UUID, delivery_result: Dict[str, Any]) -> UniversalResponse:
        """Show feedback options after successful standard delivery"""
        
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)  # FROM DATABASE!
        feedback_options = self._get_feedback_options()

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=f"{delivery_result['message']} Now, how are you feeling after completing this reflection?",
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=6, total_step=6, workflow_completed=False),
            data=[{
                "summary": current_summary,  # FROM DATABASE!
                "feedback_options": feedback_options,
                "instruction": "Select how you're feeling after this reflection experience",
                "delivery_status": delivery_result["status"]
            }]
        )

    def _show_feedback_options_after_third_party_delivery(
        self, 
        reflection_id: uuid.UUID, 
        user_id: uuid.UUID,
        recipient_email: str, 
        sender_name: str, 
        about_name: str
    ) -> UniversalResponse:
        """Show feedback options after third-party email delivery"""
        
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)  # FROM DATABASE!
        feedback_options = self._get_feedback_options()

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=f"Your reflection has been sent to {recipient_email} successfully! 📧 Now, how are you feeling after completing this reflection?",
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=6, total_step=6, workflow_completed=False),
            data=[{
                "summary": current_summary,  # FROM DATABASE!
                "feedback_options": feedback_options,
                "instruction": "Select how you're feeling after this reflection experience",
                "third_party_email_sent": True,
                "recipient": recipient_email,
                "sender": sender_name,
                "about": about_name
            }]
        )

    def _show_feedback_options(self, reflection_id: uuid.UUID, user_id: uuid.UUID) -> UniversalResponse:
        """Show feedback options when called directly (delivery already complete)"""
        
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)  # FROM DATABASE!
        feedback_options = self._get_feedback_options()

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message="How are you feeling after completing this reflection? Your feedback helps us improve Sarthi for everyone.",
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=6, total_step=6, workflow_completed=False),
            data=[{
                "summary": current_summary,  # FROM DATABASE!
                "feedback_options": feedback_options,
                "instruction": "Select how you're feeling after this reflection experience"
            }]
        )

    def _get_feedback_options(self) -> list:
        """Get feedback options from database"""
        feedback_options = self.db.query(Feedback).filter(
            Feedback.feedback_no.between(1, 5)
        ).order_by(Feedback.feedback_no).all()

        if not feedback_options:
            self.logger.error("No feedback options found in database")
            raise HTTPException(status_code=500, detail="No feedback options found in database")

        return [
            {
                "feedback": option.feedback_no,
                "text": option.feedback_text
            }
            for option in feedback_options
        ]

    def _handle_feedback_submission(self, reflection_id: uuid.UUID, user_id: uuid.UUID, feedback_choice: int) -> UniversalResponse:
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
        reflection = self._get_reflection(reflection_id, user_id)
        reflection.feedback_type = feedback_choice
        self.db.commit()
        
        # Get summary from database
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
        
        self.logger.info(f"Feedback {feedback_choice} submitted for reflection {reflection_id}")

        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=f"Thank you for your feedback! You selected: '{feedback_option.feedback_text}'. Your journey with Sarthi is now complete. 🌟",
            current_stage=100,
            next_stage=101,  # Logical completion
            progress=ProgressInfo(current_step=6, total_step=6, workflow_completed=True),
            data=[{
                "summary": current_summary,  # FROM DATABASE!
                "feedback_submitted": True,
                "feedback_choice": feedback_choice,
                "feedback_text": feedback_option.feedback_text,
                "workflow_complete": True
            }]
        )

    def _show_feedback_already_submitted(self, reflection_id: uuid.UUID, user_id: uuid.UUID, feedback_type: int) -> UniversalResponse:
        """Show message when feedback has already been submitted"""
        
        # Get summary from database
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
        
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
                "summary": current_summary,  # FROM DATABASE!
                "feedback_already_submitted": True,
                "feedback_choice": feedback_type,
                "feedback_text": feedback_text,
                "workflow_complete": True
            }]
        )