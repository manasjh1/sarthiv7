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
    """Central auth manager - handles all authentication messaging"""
    
    def __init__(self):
        self.email_provider = EmailProvider()
        self.whatsapp_provider = WhatsAppProvider()
        self.storage = AuthStorage()
        self.utils = AuthUtils()
        self.templates_path = os.path.join(os.path.dirname(__file__), "..", "templates")
    
    def send_otp(self, contact: str, invite_token: str = None, db: Session = None) -> AuthResult:
        """Send OTP - ONLY for existing users OR new users with validated invite token"""
        try:
            # Detect channel and normalize
            channel = self.utils.detect_channel(contact)
            contact = self.utils.normalize_contact(contact, channel)
            
            # Validate contact format
            if not self._validate_contact(contact, channel):
                return AuthResult(success=False, message="Invalid contact format")
            
            # Find user in database
            user = self.utils.find_user_by_contact(contact, db)
            is_existing_user = user is not None
            
            # STRICT LOGIC: Handle existing vs new users differently
            if is_existing_user:
                # ===== EXISTING USER PATH =====
                # Existing users can get OTP directly without any invite token
                logging.info(f"Existing user found for contact: {contact}")
                
                # Generate OTP for existing user
                otp = self._generate_otp()
                
                # Prepare template data
                template_data = {
                    "otp": otp,
                    "name": user.name or "User",
                    "app_name": "Sarthi"
                }
                
                # Send OTP based on channel
                if channel == "email":
                    content = self._load_template("otp_email.html", template_data)
                    metadata = {
                        "subject": f"Your Sarthi verification code: {otp}",
                        "recipient_name": template_data["name"]
                    }
                    result = self.email_provider.send(contact, content, metadata)
                elif channel == "whatsapp":
                    content = self._load_template("otp_whatsapp.txt", template_data)
                    result = self.whatsapp_provider.send(contact, content)
                else:
                    return AuthResult(success=False, message="Unsupported channel")
                
                if not result.success:
                    return AuthResult(success=False, message=f"Failed to send OTP: {result.error}")
                
                # Store OTP for existing user
                if not self.storage.store_for_existing_user(user.user_id, otp, db):
                    return AuthResult(success=False, message="Please wait 60 seconds before requesting a new OTP")
                
                return AuthResult(
                    success=True, 
                    message="OTP sent successfully. Welcome back!", 
                    contact_type=channel
                )
                
            else:
                # ===== NEW USER PATH =====
                # New users MUST have invite token to even request OTP
                if not invite_token:
                    return AuthResult(
                        success=False, 
                        message="You are a new user. Please validate your invite code first at /api/invite/validate to get an invite token, then request OTP with both contact and invite token."
                    )
                
                # Validate invite token for new user
                from app.api.invite import verify_invite_token
                from app.models import InviteCode
                
                try:
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
                        
                    logging.info(f"Valid invite token provided for new user: {contact}")
                    
                except Exception as e:
                    logging.error(f"Invite token validation failed: {str(e)}")
                    return AuthResult(success=False, message="Invalid or expired invite token. Please validate your invite code again.")
                
                # Generate OTP for new user with valid invite token
                otp = self._generate_otp()
                
                # Prepare template data for new user
                template_data = {
                    "otp": otp,
                    "name": "New User",  # New users don't have names yet
                    "app_name": "Sarthi"
                }
                
                # Send OTP based on channel
                if channel == "email":
                    content = self._load_template("otp_email.html", template_data)
                    metadata = {
                        "subject": f"Your Sarthi verification code: {otp}",
                        "recipient_name": "New User"
                    }
                    result = self.email_provider.send(contact, content, metadata)
                elif channel == "whatsapp":
                    content = self._load_template("otp_whatsapp.txt", template_data)
                    result = self.whatsapp_provider.send(contact, content)
                else:
                    return AuthResult(success=False, message="Unsupported channel")
                
                if not result.success:
                    return AuthResult(success=False, message=f"Failed to send OTP: {result.error}")
                
                # Store OTP for new user (in memory)
                if not self.storage.store_for_new_user(contact, otp):
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
        """Verify OTP and handle user creation"""
        try:
            # Detect channel and normalize
            channel = self.utils.detect_channel(contact)
            contact = self.utils.normalize_contact(contact, channel)
            
            # Find user
            user = self.utils.find_user_by_contact(contact, db)
            
            if user:
                # Existing user verification
                if channel == "whatsapp" and otp != "141414":
                    return AuthResult(success=False, message="Invalid OTP. Use 141414 for phone number verification.")
                
                if channel == "email":
                    success, message = self.storage.verify_for_existing_user(user.user_id, otp, db)
                    if not success:
                        return AuthResult(success=False, message=message)
                
                # Generate access token logic would go here
                # For now, return success
                return AuthResult(
                    success=True,
                    message="Welcome back! You have been logged in successfully.",
                    user_id=str(user.user_id),
                    is_new_user=False
                )
            else:
                # New user verification
                if not invite_token:
                    return AuthResult(success=False, message="New user registration requires a valid invite code")
                
                # Handle hardcoded phone OTP
                if channel == "whatsapp" and otp != "141414":
                    return AuthResult(success=False, message="Invalid OTP. Use 141414 for phone number verification.")
                
                # Verify OTP for email users
                if channel == "email":
                    success, message = self.storage.verify_for_new_user(contact, otp)
                    if not success:
                        return AuthResult(success=False, message=message)
                
                # Here you would handle user creation and invite token verification
                # This would involve your existing user creation logic from main.py
                
                return AuthResult(
                    success=True,
                    message="Account created successfully! Welcome to Sarthi.",
                    is_new_user=True
                )
                
        except Exception as e:
            logging.error(f"Error in verify_otp: {str(e)}")
            return AuthResult(success=False, message="Verification failed")
    
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