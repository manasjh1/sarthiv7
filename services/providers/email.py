import requests
import logging
from typing import Dict, Any
from app.config import settings
from .base import MessageProvider, SendResult

class EmailProvider(MessageProvider):
    """Email provider for sending emails via ZeptoMail"""
    
    def __init__(self):
        self.base_url = "https://api.zeptomail.in/v1.1/email"
        self.token = settings.zeptomail_token
        self.from_domain = settings.zeptomail_from_domain
        self.from_name = settings.zeptomail_from_name
        
        if not self.token:
            logging.error("ZEPTOMAIL_TOKEN not found in environment variables")
    
    def send(self, recipient: str, content: str, metadata: Dict[str, Any] = None) -> SendResult:
        """Send email via ZeptoMail - PURE SENDING LOGIC"""
        try:
            if not self.token:
                return SendResult(success=False, error="Email service not configured")
            
            subject = metadata.get("subject", "Message") if metadata else "Message"
            recipient_name = metadata.get("recipient_name", "User") if metadata else "User"
            
            payload = {
                "from": {"address": self.from_domain, "name": self.from_name},
                "to": [{"email_address": {"address": recipient, "name": recipient_name}}],
                "subject": subject,
                "htmlbody": content
            }
            
            headers = {
                'accept': "application/json",
                'content-type': "application/json",
                'authorization': self.token,
            }
            
            response = requests.post(self.base_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code in [200, 201]:
                logging.info(f"Email sent successfully to {recipient}")
                return SendResult(success=True, message_id="email_sent")
            else:
                logging.error(f"Failed to send email to {recipient}. Status: {response.status_code}, Response: {response.text}")
                return SendResult(success=False, error=f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            logging.error(f"Error sending email to {recipient}: {str(e)}")
            return SendResult(success=False, error=str(e))
    
    def validate_recipient(self, recipient: str) -> bool:
        """Validate email format"""
        return "@" in recipient and "." in recipient.split("@")[1]