import aiohttp
import asyncio
import logging
from typing import Dict, Any
from app.config import settings
from .base import MessageProvider, SendResult

class EmailProvider(MessageProvider):
    """Async Email provider for sending emails via ZeptoMail"""
    
    def __init__(self):
        self.base_url = "https://api.zeptomail.in/v1.1/email"
        self.token = settings.zeptomail_token
        self.from_domain = settings.zeptomail_from_domain
        self.from_name = settings.zeptomail_from_name
        
        if not self.token:
            logging.error("ZEPTOMAIL_TOKEN not found in environment variables")
    
    async def send(self, recipient: str, content: str, metadata: Dict[str, Any] = None) -> SendResult:
        """Send email via ZeptoMail asynchronously"""
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
            
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.base_url, json=payload, headers=headers) as response:
                    response_text = await response.text()
                    
                    if response.status in [200, 201]:
                        logging.info(f"Email sent successfully to {recipient}")
                        return SendResult(success=True, message_id="email_sent")
                    else:
                        logging.error(f"Failed to send email to {recipient}. Status: {response.status}, Response: {response_text}")
                        return SendResult(success=False, error=f"HTTP {response.status}: {response_text}")
                        
        except asyncio.TimeoutError:
            logging.error(f"Timeout sending email to {recipient}")
            return SendResult(success=False, error="Request timeout")
        except aiohttp.ClientError as e:
            logging.error(f"HTTP client error sending email to {recipient}: {str(e)}")
            return SendResult(success=False, error=f"HTTP error: {str(e)}")
        except Exception as e:
            logging.error(f"Error sending email to {recipient}: {str(e)}")
            return SendResult(success=False, error=str(e))
    
    def validate_recipient(self, recipient: str) -> bool:
        """Validate email format"""
        return "@" in recipient and "." in recipient.split("@")[1]

    # Keep synchronous version for backward compatibility if needed
    def send_sync(self, recipient: str, content: str, metadata: Dict[str, Any] = None) -> SendResult:
        """Synchronous wrapper for async send method"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, we can't use run()
                raise RuntimeError("Cannot use send_sync in an async context. Use send() instead.")
            return loop.run_until_complete(self.send(recipient, content, metadata))
        except RuntimeError:
            # Create new event loop if needed
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.send(recipient, content, metadata))
            finally:
                loop.close()