import logging
import re
from typing import Dict, Any
from app.config import settings
from .base import MessageProvider, SendResult

class WhatsAppProvider(MessageProvider):
    """WhatsApp provider for sending messages via WhatsApp Business API"""
    
    def __init__(self):
        # Use getattr to safely get settings that might not exist yet
        self.api_url = getattr(settings, 'whatsapp_api_url', '')
        self.access_token = getattr(settings, 'whatsapp_token', '')
        self.phone_id = getattr(settings, 'whatsapp_phone_id', '')
    
    def send(self, recipient: str, content: str, metadata: Dict[str, Any] = None) -> SendResult:
        """Send WhatsApp message - PURE SENDING LOGIC"""
        try:
            if not self.access_token:
                return SendResult(success=False, error="WhatsApp service not configured")
            
            # WhatsApp API call logic will go here when implemented
            # For now, just log and return success for testing
            logging.info(f"[WHATSAPP] Would send message to {recipient}: {content[:50]}...")
            return SendResult(success=True, message_id="whatsapp_sent")
                
        except Exception as e:
            logging.error(f"Error sending WhatsApp message to {recipient}: {str(e)}")
            return SendResult(success=False, error=str(e))
    
    def validate_recipient(self, recipient: str) -> bool:
        """Validate phone number format"""
        clean_number = re.sub(r'\D', '', recipient)
        return 10 <= len(clean_number) <= 15