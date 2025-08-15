import aiohttp
import asyncio
import logging
import re
import json
from typing import Dict, Any
from app.config import settings
from .base import MessageProvider, SendResult

class WhatsAppProvider(MessageProvider):
    """Async WhatsApp provider with detailed debugging"""
    
    def __init__(self):
        self.api_url = "https://crmapi.wa0.in/api/meta/v19.0"
        self.access_token = settings.whatsapp_access_token
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.template_name = settings.whatsapp_template_name
        
        if not self.access_token or not self.phone_number_id:
            logging.warning("WhatsApp API credentials not configured")
    
    async def send(self, recipient: str, content: str, metadata: Dict[str, Any] = None) -> SendResult:
        """Send WhatsApp message asynchronously with detailed debugging"""
        try:
            if not self.access_token or not self.phone_number_id:
                return SendResult(success=False, error="WhatsApp service not configured")
            
            # Normalize phone number
            normalized_phone = self._normalize_phone_number(recipient)
            if not normalized_phone:
                return SendResult(success=False, error="Invalid phone number format")
            
            # Extract OTP from content
            otp_code = self._extract_otp_from_content(content)
            if not otp_code:
                return SendResult(success=False, error="Could not extract OTP from content")
            
            # API endpoint
            url = f"{self.api_url}/{self.phone_number_id}/messages"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Payload - matching your template structure with BOTH body and button
            payload = {
                "to": normalized_phone,
                "recipient_type": "individual",
                "type": "template",
                "template": {
                    "name": self.template_name,
                    "language": {
                        "code": "en",
                        "policy": "deterministic"
                    },
                    "components": [
                        {
                            "type": "body",
                            "parameters": [
                                {
                                    "type": "text",
                                    "text": otp_code  # The OTP goes in body
                                }
                            ]
                        },
                        {
                            "type": "button",
                            "sub_type": "url", 
                            "index": 0,
                            "parameters": [
                                {
                                    "type": "text",
                                    "text": otp_code  # Same OTP goes in button parameter
                                }
                            ]
                        }
                    ]
                }
            }
            
            # DEBUG: Print request details
            print(f"\n🔍 OTP DEBUG INFO:")
            print(f"📍 URL: {url}")
            print(f"📱 To: {normalized_phone}")
            print(f"🏷️ Template: {self.template_name}")
            print(f"🔢 OTP: {otp_code}")
            print(f"📦 Payload: {json.dumps(payload, indent=2)}")
            
            # Send async request
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    response_text = await response.text()
                    
                    # DEBUG: Print full response
                    print(f"\n📊 OTP RESPONSE DEBUG:")
                    print(f"Status Code: {response.status}")
                    print(f"Headers: {dict(response.headers)}")
                    print(f"Raw Response: {response_text}")
                    
                    try:
                        response_data = json.loads(response_text)
                        print(f"Parsed JSON: {json.dumps(response_data, indent=2)}")
                    except json.JSONDecodeError:
                        print("❌ Response is not valid JSON")
                        return SendResult(success=False, error=f"Invalid JSON response: {response_text}")
                    
                    if response.status == 200:
                        # Try to extract message info
                        messages = response_data.get("messages", [])
                        if messages and len(messages) > 0:
                            message_id = messages[0].get("id", "no_id_found")
                            message_status = messages[0].get("message_status", "no_status_found")
                        else:
                            message_id = "no_messages_array"
                            message_status = "no_messages_array"
                        
                        print(f"\n✅ OTP SUCCESS DETAILS:")
                        print(f"Message ID: {message_id}")
                        print(f"Status: {message_status}")
                        
                        return SendResult(success=True, message_id=message_id)
                    else:
                        print(f"\n❌ OTP API ERROR:")
                        print(f"Status: {response.status}")
                        print(f"Response: {response_text}")
                        
                        # Try to get error details
                        if 'error' in response_data:
                            error_info = response_data['error']
                            error_msg = f"API Error {error_info.get('code', 'unknown')}: {error_info.get('message', 'unknown error')}"
                        else:
                            error_msg = f"HTTP {response.status}: {response_text}"
                        
                        return SendResult(success=False, error=error_msg)
                        
        except asyncio.TimeoutError:
            print(f"❌ OTP Timeout error")
            return SendResult(success=False, error="Request timeout")
        except aiohttp.ClientError as e:
            print(f"❌ OTP HTTP client error: {str(e)}")
            return SendResult(success=False, error=f"HTTP client error: {str(e)}")
        except Exception as e:
            print(f"❌ OTP Unexpected error: {str(e)}")
            return SendResult(success=False, error=str(e))

    async def send_reflection_summary(self, recipient: str, sender_name: str, reflection_link: str) -> SendResult:
        """Send reflection summary using the 'delivered' template"""
        try:
            if not self.access_token or not self.phone_number_id:
                return SendResult(success=False, error="WhatsApp service not configured")
            
            # Normalize phone number
            normalized_phone = self._normalize_phone_number(recipient)
            if not normalized_phone:
                return SendResult(success=False, error="Invalid phone number format")
            
            # API endpoint
            url = f"{self.api_url}/{self.phone_number_id}/messages"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Payload for 'delivered' template with 2 parameters
            payload = {
                "to": normalized_phone,
                "recipient_type": "individual",
                "type": "template",
                "template": {
                    "language": {
                        "policy": "deterministic",
                        "code": "en"
                    },
                    "name": "delivered",  # Your template name for reflection delivery
                    "components": [
                        {
                            "type": "body",
                            "parameters": [
                                {
                                    "type": "text",
                                    "text": sender_name  # First variable: sender name
                                },
                                {
                                    "type": "text", 
                                    "text": reflection_link  # Second variable: link
                                }
                            ]
                        }
                    ]
                }
            }
            
            # DEBUG: Print request details
            print(f"\n🔍 REFLECTION DELIVERY DEBUG:")
            print(f"📍 URL: {url}")
            print(f"📱 To: {normalized_phone}")
            print(f"👤 Sender: {sender_name}")
            print(f"🔗 Link: {reflection_link}")
            print(f"🏷️ Template: delivered")
            print(f"📦 Payload: {json.dumps(payload, indent=2)}")
            
            # Send async request
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    response_text = await response.text()
                    
                    # DEBUG: Print response
                    print(f"\n📊 REFLECTION DELIVERY RESPONSE:")
                    print(f"Status Code: {response.status}")
                    print(f"Headers: {dict(response.headers)}")
                    print(f"Raw Response: {response_text}")
                    
                    try:
                        response_data = json.loads(response_text)
                        print(f"Parsed JSON: {json.dumps(response_data, indent=2)}")
                    except json.JSONDecodeError:
                        print("❌ Response is not valid JSON")
                        return SendResult(success=False, error=f"Invalid JSON response: {response_text}")
                    
                    if response.status == 200:
                        # Extract message info
                        messages = response_data.get("messages", [])
                        if messages and len(messages) > 0:
                            message_id = messages[0].get("id", "no_id_found")
                            message_status = messages[0].get("message_status", "no_status_found")
                        else:
                            message_id = "no_messages_array"
                            message_status = "no_messages_array"
                        
                        print(f"\n✅ REFLECTION DELIVERY SUCCESS:")
                        print(f"Message ID: {message_id}")
                        print(f"Status: {message_status}")
                        
                        return SendResult(success=True, message_id=message_id)
                    else:
                        print(f"\n❌ REFLECTION DELIVERY ERROR:")
                        print(f"Status: {response.status}")
                        print(f"Response: {response_text}")
                        
                        # Extract error details
                        if 'error' in response_data:
                            error_info = response_data['error']
                            error_msg = f"API Error {error_info.get('code', 'unknown')}: {error_info.get('message', 'unknown error')}"
                        else:
                            error_msg = f"HTTP {response.status}: {response_text}"
                        
                        return SendResult(success=False, error=error_msg)
                        
        except asyncio.TimeoutError:
            print(f"❌ Reflection delivery timeout")
            return SendResult(success=False, error="Request timeout")
        except aiohttp.ClientError as e:
            print(f"❌ Reflection delivery HTTP error: {str(e)}")
            return SendResult(success=False, error=f"HTTP client error: {str(e)}")
        except Exception as e:
            print(f"❌ Reflection delivery unexpected error: {str(e)}")
            return SendResult(success=False, error=str(e))
    
    def validate_recipient(self, recipient: str) -> bool:
        """Validate phone number format"""
        clean_number = re.sub(r'\D', '', recipient)
        return 10 <= len(clean_number) <= 15
    
    def _normalize_phone_number(self, phone: str) -> str:
        """Normalize phone number for WhatsApp API"""
        clean_number = re.sub(r'\D', '', phone)
        
        if not clean_number:
            return ""
        
        # Handle Indian numbers
        if len(clean_number) == 10:
            clean_number = "91" + clean_number
        elif len(clean_number) == 12 and clean_number.startswith("91"):
            pass
        
        return clean_number
    
    def _extract_otp_from_content(self, content: str) -> str:
        """Extract OTP code from content"""
        # First try to find 6-digit number
        otp_pattern = r'\b\d{6}\b'
        match = re.search(otp_pattern, content)
        if match:
            return match.group()
        
        # Fallback: find any digits
        digit_pattern = r'\d+'
        matches = re.findall(digit_pattern, content)
        for match in matches:
            if len(match) >= 4:
                return match
        
        # If content is just the OTP
        clean_content = content.strip()
        if clean_content.isdigit() and len(clean_content) >= 4:
            return clean_content
        
        return content.strip()

    # Keep synchronous version for backward compatibility if needed
    def send_sync(self, recipient: str, content: str, metadata: Dict[str, Any] = None) -> SendResult:
        """Synchronous wrapper for async send method"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
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