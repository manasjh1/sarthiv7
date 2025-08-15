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
    UPDATED: Added recipient delivery support
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
            # Store request data for access in other methods
            self._current_request_data = request.data
            
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
                
                # NEW: Extract recipient contact information
                if "recipient_email" in item:
                    choices['recipient_email'] = item.get("recipient_email")
                if "recipient_phone" in item:
                    choices['recipient_phone'] = item.get("recipient_phone")
        
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
        """Show delivery mode options to user - fetch summary from DB - UPDATED with recipient input fields"""
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
        reflection = self._get_reflection(reflection_id, user_id)
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message="Perfect! How would you like to deliver your message? Please provide the recipient's contact details.",
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=5, total_step=6, workflow_completed=False),
            data=[{
                "summary": current_summary,  # FROM DATABASE!
                "delivery_options": [
                    {
                        "mode": 0, 
                        "name": "Email", 
                        "description": "Send via email",
                        "input_required": {
                            "recipient_email": {
                                "type": "email",
                                "placeholder": "Enter recipient's email address",
                                "label": "Recipient's Email",
                                "required": True
                            }
                        }
                    },
                    {
                        "mode": 1, 
                        "name": "WhatsApp", 
                        "description": "Send via WhatsApp",
                        "input_required": {
                            "recipient_phone": {
                                "type": "tel",
                                "placeholder": "Enter recipient's phone number (e.g., +1234567890)",
                                "label": "Recipient's Phone Number",
                                "required": True
                            }
                        }
                    },
                    {
                        "mode": 2, 
                        "name": "Both", 
                        "description": "Send via both email and WhatsApp",
                        "input_required": {
                            "recipient_email": {
                                "type": "email",
                                "placeholder": "Enter recipient's email address",
                                "label": "Recipient's Email",
                                "required": True
                            },
                            "recipient_phone": {
                                "type": "tel",
                                "placeholder": "Enter recipient's phone number (e.g., +1234567890)",
                                "label": "Recipient's Phone Number",
                                "required": True
                            }
                        }
                    },
                    {
                        "mode": 3, 
                        "name": "Private", 
                        "description": "Keep it private (no delivery)"
                    }
                ],
                "third_party_option": {
                    "description": "Or send to someone else's email",
                    "instruction": "Provide email in data like: {'email': 'recipient@example.com'}"
                },
                "identity_status": {
                    "is_anonymous": reflection.is_anonymous,
                    "sender_name": reflection.sender_name
                },
                "note": "Make sure you have permission to send messages to the recipient."
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
        """Handle delivery mode selection and execute delivery - UPDATED with recipient validation"""
        
        # Validate delivery mode
        if delivery_mode not in [0, 1, 2, 3]:
            raise HTTPException(status_code=400, detail="Invalid delivery mode")

        # Extract choices to get recipient contact info
        choices = self._extract_user_choices(getattr(self, '_current_request_data', []))
        
        # Validate recipient contact based on delivery mode
        if delivery_mode == 0:  # Email only
            if not choices.get('recipient_email'):
                return self._ask_for_recipient_contact(reflection_id, user_id, delivery_mode, "email")
            recipient_email = str(choices['recipient_email']).strip()  # Convert to string first
            if not self._is_valid_email(recipient_email):
                raise HTTPException(status_code=400, detail="Invalid recipient email format")
        
        elif delivery_mode == 1:  # WhatsApp only
            if not choices.get('recipient_phone'):
                return self._ask_for_recipient_contact(reflection_id, user_id, delivery_mode, "phone")
            recipient_phone = str(choices['recipient_phone']).strip()  # Convert to string first
            if not self.whatsapp_provider.validate_recipient(recipient_phone):
                raise HTTPException(status_code=400, detail="Invalid recipient phone number format")
        
        elif delivery_mode == 2:  # Both
            if not choices.get('recipient_email') or not choices.get('recipient_phone'):
                return self._ask_for_recipient_contact(reflection_id, user_id, delivery_mode, "both")
            recipient_email = str(choices['recipient_email']).strip()  # Convert to string first
            recipient_phone = str(choices['recipient_phone']).strip()  # Convert to string first
            if not self._is_valid_email(recipient_email):
                raise HTTPException(status_code=400, detail="Invalid recipient email format")
            if not self.whatsapp_provider.validate_recipient(recipient_phone):
                raise HTTPException(status_code=400, detail="Invalid recipient phone number format")

        # Update reflection with delivery mode
        reflection.delivery_mode = delivery_mode
        self.db.commit()
        
        # Get summary from database for delivery
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
        
        self.logger.info(f"Delivery mode {delivery_mode} selected for reflection {reflection_id}")

        # Use recipient-aware delivery if recipient contact provided, otherwise use old method
        if delivery_mode != 3 and (choices.get('recipient_email') or choices.get('recipient_phone')):
            delivery_result = await self._handle_delivery_with_recipient(
                delivery_mode, user, current_summary, reflection, reflection_id, choices
            )
        else:
            # Fallback to your existing delivery method for private mode or if no recipient specified
            delivery_result = await self._handle_standard_delivery(
                delivery_mode, user, current_summary, reflection, reflection_id
            )
        
        # After successful delivery, show feedback options
        return self._show_feedback_options_after_delivery(reflection_id, user_id, delivery_result)

    def _ask_for_recipient_contact(self, reflection_id: uuid.UUID, user_id: uuid.UUID, delivery_mode: int, contact_type: str) -> UniversalResponse:
        """Ask user to provide recipient contact information"""
        current_summary = self.get_reflection_summary_from_db(reflection_id, user_id)
        
        if contact_type == "email":
            message = "Please provide the recipient's email address to deliver your reflection."
            input_fields = {
                "recipient_email": {
                    "type": "email",
                    "placeholder": "Enter recipient's email address",
                    "label": "Recipient's Email",
                    "required": True
                }
            }
        elif contact_type == "phone":
            message = "Please provide the recipient's phone number to deliver your reflection via WhatsApp."
            input_fields = {
                "recipient_phone": {
                    "type": "tel",
                    "placeholder": "Enter recipient's phone number (e.g., +1234567890)",
                    "label": "Recipient's Phone Number",
                    "required": True
                }
            }
        elif contact_type == "both":
            message = "Please provide both the recipient's email address and phone number for delivery."
            input_fields = {
                "recipient_email": {
                    "type": "email",
                    "placeholder": "Enter recipient's email address",
                    "label": "Recipient's Email",
                    "required": True
                },
                "recipient_phone": {
                    "type": "tel",
                    "placeholder": "Enter recipient's phone number (e.g., +1234567890)",
                    "label": "Recipient's Phone Number",
                    "required": True
                }
            }
        
        return UniversalResponse(
            success=True,
            reflection_id=str(reflection_id),
            sarthi_message=message,
            current_stage=100,
            next_stage=100,
            progress=ProgressInfo(current_step=5, total_step=6, workflow_completed=False),
            data=[{
                "summary": current_summary,
                "delivery_mode_selected": delivery_mode,
                "input_fields": input_fields,
                "instruction": "Please provide the recipient's contact information to proceed with delivery."
            }]
        )

    async def _handle_delivery_with_recipient(
        self, 
        delivery_mode: int, 
        sender_user: User, 
        summary: str,
        reflection: Reflection = None,
        reflection_id: uuid.UUID = None,
        choices: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Handle delivery with recipient contact info"""
        delivery_status = []
        
        try:
            if delivery_mode == 0:  # Email only
                recipient_email = choices.get('recipient_email')
                await self._deliver_to_recipient_email(
                    sender_user, summary, delivery_status, reflection, reflection_id, recipient_email
                )
                message = f"Your message has been sent via email to {recipient_email} successfully! 📧"
                
            elif delivery_mode == 1:  # WhatsApp only
                recipient_phone = choices.get('recipient_phone')
                await self._deliver_to_recipient_whatsapp(
                    sender_user, summary, delivery_status, reflection, reflection_id, recipient_phone
                )
                message = f"Your message has been sent via WhatsApp to {recipient_phone} successfully! 📱"
                
            elif delivery_mode == 2:  # Both email and WhatsApp
                recipient_email = choices.get('recipient_email')
                recipient_phone = choices.get('recipient_phone')
                sent_methods = []
                
                await self._deliver_to_recipient_both(
                    sender_user, summary, delivery_status, sent_methods, 
                    reflection, reflection_id, recipient_email, recipient_phone
                )
                
                if not sent_methods:
                    raise HTTPException(
                        status_code=400, 
                        detail="Both delivery methods failed"
                    )
                
                message = f"Your message has been sent via {' and '.join(sent_methods)} successfully! 📧📱"
            
            self.logger.info(f"Recipient delivery completed - Status: {delivery_status}, Message: {message}")
            
            return {
                "status": delivery_status,
                "message": message
            }
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Recipient delivery failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Message delivery failed: {str(e)}")

    async def _deliver_to_recipient_email(
        self, 
        sender_user: User,
        summary: str, 
        delivery_status: list,
        reflection: Reflection = None,
        reflection_id: uuid.UUID = None,
        recipient_email: str = None
    ):
        """Deliver message via email to specific recipient"""
        if not recipient_email:
            raise HTTPException(status_code=400, detail="Recipient email not provided")

        # Ensure recipient_email is a string
        recipient_email = str(recipient_email).strip()
        
        self.logger.info(f"Attempting email delivery to recipient: {recipient_email}")

        # Create recipient user
        if reflection and reflection_id:
            await self._create_or_update_recipient_user(
                contact=recipient_email, 
                reflection=reflection,
                reflection_id=reflection_id
            )
        
        # Get sender name for email
        sender_name = self._get_sender_name(reflection, sender_user) if reflection else "Someone"
        
        # Send reflection via email
        result = await self.auth_manager.send_feedback_email(
            sender_name=sender_name,
            receiver_name=reflection.name or "Recipient",
            receiver_email=recipient_email,
            feedback_summary=summary
        )
        
        if not result.success:
            raise HTTPException(status_code=500, detail=f"Email sending failed: {result.error}")
            
        delivery_status.append("email_sent")
        self.logger.info(f"✅ Email sent successfully to recipient: {recipient_email}")

    async def _deliver_to_recipient_whatsapp(
        self, 
        sender_user: User, 
        summary: str, 
        delivery_status: list,
        reflection: Reflection = None,
        reflection_id: uuid.UUID = None,
        recipient_phone: str = None
    ):
        """Deliver reflection summary via WhatsApp to specific recipient"""
        if not recipient_phone:
            raise HTTPException(status_code=400, detail="Recipient phone number not provided")

        # Ensure recipient_phone is a string
        recipient_phone = str(recipient_phone).strip()
        
        self.logger.info(f"Attempting WhatsApp reflection delivery to recipient: {recipient_phone}")

        # Create recipient user
        if reflection and reflection_id:
            await self._create_or_update_recipient_user(
                contact=recipient_phone, 
                reflection=reflection,
                reflection_id=reflection_id
            )
        
        # Generate reflection link
        reflection_link = f"https://app.sarthi.me/reflection/{reflection_id}"
        
        # Get sender name for WhatsApp template
        sender_name = self._get_sender_name(reflection, sender_user) if reflection else "Someone"
        
        # Use the template-based delivery to RECIPIENT (your send_reflection_summary method)
        result = await self.whatsapp_provider.send_reflection_summary(
            recipient=recipient_phone,  # ← RECIPIENT's phone
            sender_name=sender_name,    # ← SENDER's name
            reflection_link=reflection_link
        )
        
        if not result.success:
            raise HTTPException(status_code=500, detail=f"WhatsApp reflection delivery failed: {result.error}")
            
        delivery_status.append("whatsapp_sent")
        self.logger.info(f"✅ Reflection sent via WhatsApp to recipient: {recipient_phone}")

    async def _deliver_to_recipient_both(
        self, 
        sender_user: User, 
        summary: str, 
        delivery_status: list, 
        sent_methods: list,
        reflection: Reflection = None,
        reflection_id: uuid.UUID = None,
        recipient_email: str = None,
        recipient_phone: str = None
    ):
        """Deliver message via both email and WhatsApp to specific recipient"""

        # Ensure both are strings
        if recipient_email:
            recipient_email = str(recipient_email).strip()
        if recipient_phone:
            recipient_phone = str(recipient_phone).strip()
        
        # Try email delivery
        if recipient_email:
            try:
                await self._deliver_to_recipient_email(
                    sender_user, summary, [], reflection, reflection_id, recipient_email
                )
                delivery_status.append("email_sent")
                sent_methods.append("email")
                self.logger.info("Email sent successfully to recipient in Both mode")
            except Exception as e:
                self.logger.warning(f"Email exception in Both mode: {str(e)}")

        # Try WhatsApp delivery
        if recipient_phone:
            try:
                await self._deliver_to_recipient_whatsapp(
                    sender_user, summary, [], reflection, reflection_id, recipient_phone
                )
                delivery_status.append("whatsapp_sent")
                sent_methods.append("WhatsApp")
                self.logger.info("WhatsApp reflection sent successfully to recipient in Both mode")
            except Exception as e:
                self.logger.warning(f"WhatsApp reflection exception in Both mode: {str(e)}")

    async def _handle_standard_delivery(
        self, 
        delivery_mode: int, 
        user: User, 
        summary: str,
        reflection: Reflection = None,  # Add these parameters!
        reflection_id: uuid.UUID = None  # Add these parameters!
) -> Dict[str, Any]:
        """Handle standard delivery modes with comprehensive error handling and logging"""
        delivery_status = []
        
        try:
            if delivery_mode == 0:  # Email only
                await self._deliver_via_email(user, summary, delivery_status,reflection, reflection_id)
                message = "Your message has been sent via email successfully! 📧"
                
            elif delivery_mode == 1:  # WhatsApp only
                await self._deliver_via_whatsapp(user, summary, delivery_status, reflection, reflection_id)
                message = "Your message has been sent via WhatsApp successfully! 📱"
                
            elif delivery_mode == 2:  # Both email and WhatsApp
                sent_methods = []
                await self._deliver_via_both(user, summary, delivery_status, sent_methods, reflection, reflection_id)
                
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
        

    async def _create_or_update_recipient_user(
        self, 
        contact: str,
        reflection: Reflection,  # Existing reflection - NOT creating new one
        reflection_id: uuid.UUID  # Existing reflection_id - just for logging
    ):
        """
        Create a new USER entry for the recipient if they don't exist
        This does NOT create a reflection - the reflection already exists!
        We're just linking it to a recipient user
        """
        try:
            # Use the existing auth utils to detect and normalize contact
            contact_type = self.auth_manager.utils.detect_channel(contact)
            normalized_contact = self.auth_manager.utils.normalize_contact(contact, contact_type)
            
            self.logger.info(f"Checking/creating recipient user - Contact: {contact}, Type: {contact_type}")
            
            # Find if a user with this contact already exists
            existing_user = self.auth_manager.utils.find_user_by_contact(normalized_contact, self.db)
            
            if not existing_user:
                # Create new USER (not reflection!) for the recipient who doesn't have an account
                new_user_id = uuid.uuid4()  # Generate new user_id
                
                new_recipient_user = User(
                    user_id=new_user_id,  # NEW USER ID - this is what we're creating!
                    email=normalized_contact if contact_type == "email" else None,
                    phone_number=int(normalized_contact) if contact_type == "whatsapp" and normalized_contact.isdigit() else None,
                    name=reflection.name if reflection.name else None,  # Name from reflection
                    user_type='user',
                    is_verified=False,  # False because they haven't signed up yet
                    is_anonymous=None,  # Not decided yet
                    proficiency_score=0,
                    status=1
                )
                
                self.db.add(new_recipient_user)
                self.db.commit()
                self.db.refresh(new_recipient_user)
                
                # Link the EXISTING reflection to this NEW user as the receiver
                reflection.receiver_user_id = new_recipient_user.user_id
                self.db.commit()
                
                contact_display = f"email: {normalized_contact}" if contact_type == "email" else f"phone: {normalized_contact}"
                self.logger.info(f"✅ Created new USER (not reflection!) with user_id: {new_user_id} for {contact_display}")
                self.logger.info(f"✅ Linked existing reflection {reflection_id} to new receiver user_id: {new_user_id}")
                
            else:
                # User already exists - just link the reflection to them
                reflection.receiver_user_id = existing_user.user_id
                self.db.commit()
                
                contact_display = f"email: {normalized_contact}" if contact_type == "email" else f"phone: {normalized_contact}"
                verification_status = "VERIFIED" if existing_user.is_verified else "UNVERIFIED"
                self.logger.info(f"📌 Recipient {contact_display} already has user_id: {existing_user.user_id} ({verification_status})")
                self.logger.info(f"📌 Linked existing reflection {reflection_id} to existing user_id: {existing_user.user_id}")
                
        except Exception as e:
            self.logger.error(f"Error creating/updating recipient user for {contact}: {str(e)}")
            self.db.rollback()


    async def _deliver_via_email(
        self, 
        user: User,  # The SENDER user (or could be the recipient user object)
        summary: str, 
        delivery_status: list,
        reflection: Reflection = None,  # EXISTING reflection
        reflection_id: uuid.UUID = None  # EXISTING reflection_id
):
        """Deliver message via email"""
        if not user.email:
            raise HTTPException(status_code=400, detail="User email not available")
        
        self.logger.info(f"Attempting email delivery to {user.email}")

        # Create or update RECIPIENT USER (not reflection!)
        if reflection and reflection_id:
            await self._create_or_update_recipient_user(
                contact=user.email, 
                reflection=reflection,  # Pass EXISTING reflection
                reflection_id=reflection_id  # Pass EXISTING reflection_id for logging
            )
        
        metadata = {
            "subject": "Your Sarthi Reflection Summary",
            "recipient_name": user.name or "User"
        }
        
        result = await self.email_provider.send(user.email, summary, metadata)
        
        self.logger.info(f"Email result - Success: {result.success}, Error: {result.error if not result.success else 'None'}")
        
        if not result.success:
            raise HTTPException(status_code=500, detail=f"Email sending failed: {result.error}")
            
        delivery_status.append("email_sent")
        self.logger.info(f"✅ Email sent successfully to {user.email}")
        

    async def _deliver_via_whatsapp(
        self, 
        user: User, 
        summary: str, 
        delivery_status: list,
        reflection: Reflection = None,  # Add these parameters!
        reflection_id: uuid.UUID = None  # Add these parameters!
):
        """Deliver message via WhatsApp"""
        if not user.phone_number:
            raise HTTPException(status_code=400, detail="User phone number not available")
        
        self.logger.info(f"Attempting WhatsApp delivery to {user.phone_number}")

        # FIXED: Now create user for WhatsApp delivery too!
        if reflection and reflection_id:
            await self._create_or_update_recipient_user(
                contact=str(user.phone_number), 
                reflection=reflection,
                reflection_id=reflection_id
            )
        
        result = await self.whatsapp_provider.send(str(user.phone_number), summary)
        
        self.logger.info(f"WhatsApp result - Success: {result.success}, Error: {result.error if not result.success else 'None'}")
        
        if not result.success:
            raise HTTPException(status_code=500, detail=f"WhatsApp sending failed: {result.error}")
            
        delivery_status.append("whatsapp_sent")

    async def _deliver_via_both(
        self, 
        user: User, 
        summary: str, 
        delivery_status: list, 
        sent_methods: list,
        reflection: Reflection = None,  # Add these parameters!
        reflection_id: uuid.UUID = None  # Add these parameters!
):
        """Deliver message via both email and WhatsApp"""
        
        # Try email delivery
        if user.email:
            try:
                self.logger.info(f"Attempting email delivery to {user.email} (Both mode)")

                # FIXED: Create user for email
                if reflection and reflection_id:
                    await self._create_or_update_recipient_user(
                        contact=user.email,
                        reflection=reflection,
                        reflection_id=reflection_id
                    )

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

                # FIXED: Create user for WhatsApp
                if reflection and reflection_id:
                    await self._create_or_update_recipient_user(
                        contact=str(user.phone_number),
                        reflection=reflection,
                        reflection_id=reflection_id
                    )

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

            # FIXED: Create user for third-party recipient!
            await self._create_or_update_recipient_user(
                contact=recipient_email,
                reflection=reflection,
                reflection_id=reflection_id
            )

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
        if not email:
            return False
        
        # Convert to string and strip whitespace
        email_str = str(email).strip()
        
        if not email_str:
            return False
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email_str) is not None

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