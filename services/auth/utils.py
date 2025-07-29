import re
from typing import Optional
from sqlalchemy.orm import Session
from app.models import User

class AuthUtils:
    """Utilities for authentication operations"""
    
    def detect_channel(self, contact: str) -> str:
        """Detect channel based on contact format"""
        contact = contact.strip()
        
        if "@" in contact:
            return "email"
        else:
            # Phone number - will use WhatsApp
            return "whatsapp"
    
    def normalize_contact(self, contact: str, channel: str) -> str:
        """Normalize contact format"""
        if channel == "email":
            return contact.strip().lower()
        elif channel == "whatsapp":
            # Remove all non-digit characters for phone
            clean_number = re.sub(r'\D', '', contact)
            return clean_number
        return contact
    
    def find_user_by_contact(self, contact: str, db: Session) -> Optional[User]:
        """Find user by email or phone with flexible matching"""
        contact = contact.strip()
        user = None
        
        if "@" in contact:
            # Email lookup
            user = db.query(User).filter(
                User.email == contact.lower(),
                User.status == 1
            ).first()
        else:
            # Phone lookup with flexible matching
            clean_contact = ''.join(filter(str.isdigit, contact))
            if clean_contact:
                try:
                    # Try exact match first
                    phone_number = int(clean_contact)
                    user = db.query(User).filter(
                        User.phone_number == phone_number,
                        User.status == 1
                    ).first()
                    
                    # Try without country code
                    if not user and len(clean_contact) > 10:
                        local_number = int(clean_contact[-10:])
                        user = db.query(User).filter(
                            User.phone_number == local_number,
                            User.status == 1
                        ).first()
                    
                    # Try with common country codes
                    if not user and len(clean_contact) == 10:
                        for country_code in ['1', '91']:  # US, India
                            full_number = int(country_code + clean_contact)
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
       import re
    
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
       import re
       sanitized = re.sub(r'[<>"\']', '', name.strip())
    
       # Limit length
       if len(sanitized) > 50:
        sanitized = sanitized[:50] + "..."
    
       return sanitized or "User"