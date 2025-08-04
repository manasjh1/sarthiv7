import os
import random
import string
import logging
from typing import Optional
from dataclasses import dataclass
from jinja2 import Template
from sqlalchemy.orm import Session
from services.providers.email import EmailProvider
from services.providers.whatsapp import WhatsAppProvider
from .storage import AuthStorage
from .utils import AuthUtils

@dataclass
class AuthResult:
    """Result class for auth operations"""
    success: bool
    message: str
    contact_type: Optional[str] = None
    access_token: Optional[str] = None
    user_id: Optional[str] = None
    is_new_user: Optional[bool] = None
    error_code: Optional[str] = None

class AuthManager:
    """Central auth manager - handles all authentication messaging with async support"""
    
    def __init__(self):
        self.email_provider = EmailProvider()
        self.whatsapp_provider = WhatsAppProvider()
        self.storage = AuthStorage()
        self.utils = AuthUtils()
        self.templates_path = os.path.join(os.path.dirname(__file__), "..", "templates")
    
    async def send_otp(self, contact: str, invite_token: str = None, db: Session = None) -> AuthResult:
        """Send OTP asynchronously - ONLY for existing users OR new users with validated invite token"""
        try:
            # Detect channel and normalize CONSISTENTLY
            channel = self.utils.detect_channel(contact)
            normalized_contact = self.utils.normalize_contact(contact, channel)
            
            # Log normalization for debugging
            logging.info(f"🔍 SEND_OTP: Original='{contact}' -> Normalized='{normalized_contact}' (Channel: {channel})")
            
            # Validate contact format
            if not self._validate_contact(normalized_contact, channel):
                return AuthResult(success=False, message="Invalid contact format")
            
            # Find user in database using normalized contact
            user = self.utils.find_user_by_contact(normalized_contact, db)
            is_existing_user = user is not None
            
            logging.info(f"🔍 User lookup result: Existing={is_existing_user}")
            
            # STRICT LOGIC: Handle existing vs new users differently
            if is_existing_user:
                # ===== EXISTING USER PATH =====
                try:
                    user_id_str = str(user.user_id)
                    logging.info(f"Existing user found for contact: {normalized_contact}, user_id: {user_id_str}")
                except Exception as e:
                    logging.error(f"Error converting user_id to string: {e}")
                    user_id_str = "unknown"
                
                # Generate OTP for existing user
                otp = self._generate_otp()
                logging.info(f"🔍 Generated OTP for existing user: {otp}")
                
                # Send OTP based on channel - ASYNC
                if channel == "email":
                    template_data = {
                        "otp": otp,
                        "name": user.name or "User",
                        "app_name": "Sarthi"
                    }
                    content = self._load_template("otp_email.html", template_data)
                    metadata = {
                        "subject": f"Your Sarthi verification code: {otp}",
                        "recipient_name": template_data["name"]
                    }
                    result = await self.email_provider.send(normalized_contact, content, metadata)
                elif channel == "whatsapp":
                    result = await self.whatsapp_provider.send(normalized_contact, otp)
                else:
                    return AuthResult(success=False, message="Unsupported channel")
                
                if not result.success:
                    return AuthResult(success=False, message=f"Failed to send OTP: {result.error}")
                
                # Store OTP for existing user (pass UUID to storage)
                if not self.storage.store_for_existing_user(user.user_id, otp, db):
                    return AuthResult(success=False, message="Please wait 60 seconds before requesting a new OTP")
                
                return AuthResult(
                    success=True, 
                    message="OTP sent successfully. Welcome back!", 
                    contact_type=channel
                )
                
            else:
                # ===== NEW USER PATH =====
                if not invite_token:
                    return AuthResult(
                        success=False, 
                        message="You are a new user. Please validate your invite code first at /api/invite/validate to get an invite token, then request OTP with both contact and invite token."
                    )
                
                # Validate invite token for new user
                try:
                    from app.api.invite import verify_invite_token
                    from app.models import InviteCode
                    
                    # Verify the invite JWT token
                    invite_data = verify_invite_token(invite_token)
                    
                    # Check if invite code exists and is still available
                    invite = db.query(InviteCode).filter(
                        InviteCode.invite_id == invite_data["invite_id"],
                        InviteCode.invite_code == invite_data["invite_code"]
                    ).first()
                    
                    if not invite:
                        return AuthResult(success=False, message="Invalid invite token")
                    
                    if invite.is_used and invite.user_id:
                        return AuthResult(success=False, message="This invite code has already been used by another user")
                        
                    logging.info(f"✅ Valid invite token provided for new user: {normalized_contact}")

                except Exception as e:
                    logging.error(f"Invite token validation failed: {str(e)}")
                    return AuthResult(success=False, message="You are a new user. Please enter your valid invite code to continue.")
                
                # Generate OTP for new user with valid invite token
                otp = self._generate_otp()
                logging.info(f"🔍 Generated OTP for new user: {otp}")
                
                # Send OTP based on channel - ASYNC
                if channel == "email":
                    template_data = {
                        "otp": otp,
                        "name": "New User",
                        "app_name": "Sarthi"
                    }
                    content = self._load_template("otp_email.html", template_data)
                    metadata = {
                        "subject": f"Your Sarthi verification code: {otp}",
                        "recipient_name": "New User"
                    }
                    result = await self.email_provider.send(normalized_contact, content, metadata)
                elif channel == "whatsapp":
                    result = await self.whatsapp_provider.send(normalized_contact, otp)
                else:
                    return AuthResult(success=False, message="Unsupported channel")
                
                if not result.success:
                    return AuthResult(success=False, message=f"Failed to send OTP: {result.error}")
                
                # Store OTP for new user using NORMALIZED contact
                if not self.storage.store_for_new_user(normalized_contact, otp):
                    return AuthResult(success=False, message="Please wait 60 seconds before requesting a new OTP")
                
                return AuthResult(
                    success=True, 
                    message="OTP sent successfully. Please complete registration with the OTP and your invite token.", 
                    contact_type=channel
                )
            
        except Exception as e:
            logging.error(f"Error in send_otp: {str(e)}")
            return AuthResult(success=False, message="Failed to send OTP")
    
    def verify_otp(self, contact: str, otp: str, invite_token: str = None, db: Session = None) -> AuthResult:
        """Verify OTP and handle user creation (synchronous - no external calls)"""
        try:
            # Detect channel and normalize CONSISTENTLY
            channel = self.utils.detect_channel(contact)
            normalized_contact = self.utils.normalize_contact(contact, channel)
            
            # Log normalization for debugging
            logging.info(f"🔍 VERIFY_OTP: Original='{contact}' -> Normalized='{normalized_contact}' (Channel: {channel})")
            
            # Find user using normalized contact
            user = self.utils.find_user_by_contact(normalized_contact, db)
            
            if user:
                # ===== EXISTING USER VERIFICATION =====
                try:
                    user_id_str = str(user.user_id)
                    logging.info(f"🔍 Verifying OTP for existing user: {user_id_str}")
                except Exception as e:
                    logging.error(f"Error converting user_id to string: {e}")
                    user_id_str = "unknown"
                
                success, message = self.storage.verify_for_existing_user(user.user_id, otp, db)
                if not success:
                    return AuthResult(success=False, message=message)
                
                return AuthResult(
                    success=True,
                    message="Welcome back! You have been logged in successfully.",
                    user_id=user_id_str,
                    is_new_user=False
                )
            else:
                # ===== NEW USER VERIFICATION =====
                if not invite_token:
                    return AuthResult(success=False, message="New user registration requires a valid invite code")
                
                logging.info(f"🔍 Verifying OTP for new user: {normalized_contact}")
                
                # Verify OTP using NORMALIZED contact
                success, message = self.storage.verify_for_new_user(normalized_contact, otp)
                if not success:
                    return AuthResult(success=False, message=message)
                
                return AuthResult(
                    success=True,
                    message="Account created successfully! Welcome to Sarthi.",
                    is_new_user=True
                )
                
        except Exception as e:
            logging.error(f"Error in verify_otp: {str(e)}")
            return AuthResult(success=False, message="Verification failed")
    
    async def send_feedback_email(self, sender_name: str, receiver_name: str, receiver_email: str, feedback_summary: str) -> AuthResult:
        """Send feedback email with 20%-80% split - ASYNC"""
        try:
            logging.info(f"Sending feedback email to: {receiver_email}")
            
            # Simple 20%-80% split
            split_point = int(len(feedback_summary) * 0.2)
            feedback_preview = feedback_summary[:split_point]
            feedback_remaining = feedback_summary[split_point:]
            
            # Template data
            template_data = {
                "sender_name": sender_name,
                "receiver_name": receiver_name,
                "feedback_preview": feedback_preview,
                "feedback_remaining": feedback_remaining
            }
            
            # Load template and send email - ASYNC
            content = self._load_template("feedback_email.html", template_data)
            metadata = {
                "subject": f"You have feedback from {sender_name}",
                "recipient_name": receiver_name
            }
            
            result = await self.email_provider.send(receiver_email, content, metadata)
            
            if result.success:
                return AuthResult(success=True, message=f"Feedback email sent successfully to {receiver_email}")
            else:
                logging.error(f"Email send failed: {result.error}")
                return AuthResult(success=False, message=f"Failed to send feedback email: {result.error}")
                
        except Exception as e:
            logging.error(f"Exception in send_feedback_email: {str(e)}")
            return AuthResult(success=False, message=f"Failed to send feedback email: {str(e)}")
    
    def _load_template(self, template_file: str, data: dict) -> str:
        """Load template from services/templates/"""
        template_path = os.path.join(self.templates_path, template_file)
        
        with open(template_path, 'r') as f:
            template_content = f.read()
        
        template = Template(template_content)
        return template.render(**data)
    
    def _validate_contact(self, contact: str, channel: str) -> bool:
        """Validate contact using appropriate provider"""
        if channel == "email":
            return self.email_provider.validate_recipient(contact)
        elif channel == "whatsapp":
            return self.whatsapp_provider.validate_recipient(contact)
        return False
    
    def _generate_otp(self) -> str:
        """Generate 6-digit OTP"""
        return ''.join(random.choices(string.digits, k=6))