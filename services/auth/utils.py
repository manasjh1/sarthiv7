import re
from typing import Optional
from sqlalchemy.orm import Session
from app.models import User

class AuthUtils:
    """Utilities for authentication operations with consistent contact normalization"""
    
    def detect_channel(self, contact: str) -> str:
        """Detect channel based on contact format"""
        contact = contact.strip()
        
        if "@" in contact:
            return "email"
        else:
            return "whatsapp"
    
    def normalize_contact(self, contact: str, channel: str) -> str:
        """
        CRITICAL: Normalize contact format CONSISTENTLY 
        This MUST match the logic in services/auth/storage.py
        """
        if not contact:
            return ""
            
        contact = contact.strip()
        
        if channel == "email":
            # Email: lowercase and strip whitespace
            return contact.lower()
        elif channel == "whatsapp":
            # Phone: remove ALL non-digit characters (spaces, dashes, plus signs, etc.)
            clean_number = re.sub(r'\D', '', contact)
            return clean_number
        return contact.strip()
    
    def normalize_contact_auto(self, contact: str) -> str:
        """
        Auto-detect channel and normalize consistently
        Use this when you don't know the channel type
        """
        channel = self.detect_channel(contact)
        return self.normalize_contact(contact, channel)
    
    def find_user_by_contact(self, contact: str, db: Session) -> Optional[User]:
        """Find user by email or phone with flexible matching"""
        # First normalize the contact consistently
        normalized_contact = self.normalize_contact_auto(contact)
        user = None
        
        if "@" in normalized_contact:
            # Email lookup - use normalized (lowercase) email
            user = db.query(User).filter(
                User.email == normalized_contact,
                User.status == 1
            ).first()
        else:
            # Phone lookup - normalized contact is clean digits only
            if normalized_contact and normalized_contact.isdigit():
                try:
                    # Try exact match first
                    phone_number = int(normalized_contact)
                    user = db.query(User).filter(
                        User.phone_number == phone_number,
                        User.status == 1
                    ).first()
                    
                    # Try without country code if number is long
                    if not user and len(normalized_contact) > 10:
                        local_number = int(normalized_contact[-10:])
                        user = db.query(User).filter(
                            User.phone_number == local_number,
                            User.status == 1
                        ).first()
                    
                    # Try with common country codes if number is 10 digits
                    if not user and len(normalized_contact) == 10:
                        for country_code in ['1', '91']:  # US, India
                            full_number = int(country_code + normalized_contact)
                            user = db.query(User).filter(
                                User.phone_number == full_number,
                                User.status == 1
                            ).first()
                            if user:
                                break
                except ValueError:
                    pass
        
        return user
    
    def validate_email_format(self, email: str) -> bool:
        """Validate email format for feedback emails"""
        if not email or not isinstance(email, str):
            return False
    
        # Basic email validation pattern
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email.strip()) is not None
   
    def extract_email_from_request_data(self, request_data: list) -> str:
        """Extract email from request data"""
        if not request_data or not isinstance(request_data, list):
            return None
    
        for item in request_data:
            if isinstance(item, dict) and "email" in item:
                email = item.get("email", "").strip()
                if self.validate_email_format(email):
                    return email

        return None
   
    def sanitize_name_for_email(self, name: str) -> str:
        """Sanitize name for use in email templates"""
        if not name or not isinstance(name, str):
            return "User"
    
        # Remove any potentially harmful characters
        sanitized = re.sub(r'[<>"\']', '', name.strip())
    
        # Limit length
        if len(sanitized) > 50:
            sanitized = sanitized[:50] + "..."
    
        return sanitized or "User"