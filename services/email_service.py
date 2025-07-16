import requests
import random
import string
import os
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.models import OTPToken, User, InviteCode
import uuid

@dataclass
class OTPResult:
    """Result class for OTP operations"""
    success: bool
    message: str
    error_code: Optional[str] = None

# ✅ MEMORY STORAGE FOR NEW USERS (before registration)
new_user_otps: Dict[str, Dict] = {}

class ZeptoMailService:
    """
    EXACT NEW USER FLOW:
    1. Validate invite code → get JWT
    2. Send OTP (with JWT) → store in memory
    3. Verify OTP (with JWT) → create user + MOVE OTP to database + mark invite as used
    """
    
    def __init__(self):
        self.base_url = "https://api.zeptomail.in/v1.1/email"
        self.token = os.getenv("ZEPTOMAIL_TOKEN")
        self.from_domain = os.getenv("ZEPTOMAIL_FROM_DOMAIN", "noreply@sarthi.me")
        self.from_name = os.getenv("ZEPTOMAIL_FROM_NAME", "Sarthi")
        
        if not self.token:
            logging.error("ZEPTOMAIL_TOKEN not found in environment variables")
    
    def _generate_otp(self) -> str:
        """Generate a 6-digit OTP"""
        return ''.join(random.choices(string.digits, k=6))
    
    def _get_otp_template(self, otp: str, recipient_name: str = "User") -> str:
        """Get HTML template for OTP email"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Your OTP Code</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #333333; margin: 0; font-size: 32px; font-weight: 300;">Sarthi</h1>
                    <p style="color: #666666; margin: 5px 0 0 0; font-size: 16px;">Your personal reflection companion</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 30px; border-radius: 10px; text-align: center;">
                    <h2 style="color: #333333; margin: 0 0 20px 0;">Your Verification Code</h2>
                    <p style="color: #666666; margin: 0 0 20px 0;">Hi {recipient_name},</p>
                    <p style="color: #666666; margin: 0 0 30px 0;">Use this code to complete your sign-in:</p>
                    
                    <div style="background-color: #ffffff; border: 2px solid #e9ecef; border-radius: 8px; padding: 20px; margin: 20px 0; display: inline-block;">
                        <span style="font-size: 32px; font-weight: bold; color: #333333; letter-spacing: 5px;">{otp}</span>
                    </div>
                    
                    <p style="color: #999999; font-size: 14px; margin: 20px 0 0 0;">
                        This code expires in 3 minutes.<br>
                        If you didn't request this code, please ignore this email.
                    </p>
                </div>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e9ecef;">
                    <p style="color: #999999; font-size: 12px; margin: 0;">
                        This is an automated message from Sarthi. Please do not reply to this email.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def send_otp(self, user_id: uuid.UUID, email: str, db: Session, recipient_name: str = "User") -> OTPResult:
        """
        Send OTP to EXISTING user - Database storage
        ✅ Replace old OTP with new OTP (individual user management)
        """
        try:
            if not self.token:
                return OTPResult(
                    success=False,
                    message="Email service not configured",
                    error_code="CONFIG_ERROR"
                )
            
            # ✅ CHECK COOLDOWN - Only for this specific user
            existing_otp = db.query(OTPToken).filter(OTPToken.user_id == user_id).first()
            if existing_otp:
                time_since_creation = datetime.utcnow() - existing_otp.created_at
                if time_since_creation < timedelta(minutes=1):
                    remaining_seconds = 60 - int(time_since_creation.total_seconds())
                    return OTPResult(
                        success=False,
                        message=f"Please wait {remaining_seconds} seconds before requesting a new OTP",
                        error_code="COOLDOWN_ACTIVE"
                    )
                
                # ✅ REPLACE: Delete THIS user's old OTP only
                try:
                    db.delete(existing_otp)
                    db.flush()  # Ensure deletion is processed before adding new one
                    logging.info(f"Deleted old OTP for existing user {user_id}")
                except SQLAlchemyError as e:
                    db.rollback()
                    logging.error(f"Failed to delete old OTP for user {user_id}: {str(e)}")
                    return OTPResult(
                        success=False,
                        message="Failed to process OTP request",
                        error_code="DB_DELETE_FAILED"
                    )
            
            # Generate new OTP
            otp = self._generate_otp()
            
            # Send email first
            if not self._send_email(email, otp, recipient_name):
                return OTPResult(
                    success=False,
                    message="Failed to send OTP email",
                    error_code="EMAIL_SEND_FAILED"
                )
            
            # ✅ STORE NEW OTP in database with explicit error handling
            try:
                otp_token = OTPToken(
                    user_id=user_id,
                    otp=otp,
                    created_at=datetime.utcnow()  # Explicitly set creation time
                )
                db.add(otp_token)
                db.commit()
                
                logging.info(f"OTP successfully sent and stored in database for existing user {user_id}")
                return OTPResult(success=True, message="OTP sent successfully")
                
            except SQLAlchemyError as db_error:
                db.rollback()
                logging.error(f"Database error storing OTP for user {user_id}: {str(db_error)}")
                return OTPResult(
                    success=False,
                    message="Failed to store OTP in database",
                    error_code="DB_STORAGE_FAILED"
                )
                
        except Exception as e:
            logging.error(f"Unexpected error in send_otp for user {user_id}: {str(e)}")
            db.rollback()
            return OTPResult(
                success=False,
                message="Failed to send OTP",
                error_code="UNEXPECTED_ERROR"
            )

    def send_otp_for_new_user(self, email: str, db: Session, recipient_name: str = "User") -> OTPResult:
        """
        Send OTP to NEW user - Memory storage
        ✅ Store in memory with invite info for later database transfer
        """
        try:
            if not self.token:
                return OTPResult(
                    success=False,
                    message="Email service not configured",
                    error_code="CONFIG_ERROR"
                )
            
            email = email.lower()
            
            # ✅ CHECK COOLDOWN - Same as database approach
            if email in new_user_otps:
                time_since_creation = datetime.utcnow() - new_user_otps[email]['created_at']
                if time_since_creation < timedelta(minutes=1):
                    remaining_seconds = 60 - int(time_since_creation.total_seconds())
                    return OTPResult(
                        success=False,
                        message=f"Please wait {remaining_seconds} seconds before requesting a new OTP",
                        error_code="COOLDOWN_ACTIVE"
                    )
                
                logging.info(f"Replacing old OTP for new user {email}")
            
            # Generate new OTP
            otp = self._generate_otp()
            
            # Send email
            if self._send_email(email, otp, recipient_name):
                # ✅ STORE IN MEMORY with all info needed for database transfer
                new_user_otps[email] = {
                    'otp': otp,
                    'created_at': datetime.utcnow(),
                    'email': email,
                    'recipient_name': recipient_name
                }
                
                logging.info(f"New OTP sent and stored in memory for new user {email}")
                return OTPResult(success=True, message="OTP sent successfully to your email")
            else:
                return OTPResult(
                    success=False,
                    message="Failed to send OTP email",
                    error_code="EMAIL_SEND_FAILED"
                )
                
        except Exception as e:
            logging.error(f"Error in send_otp_for_new_user for {email}: {str(e)}")
            return OTPResult(
                success=False,
                message="Failed to send OTP",
                error_code="UNEXPECTED_ERROR"
            )

    def verify_otp(self, user_id: uuid.UUID, otp: str, db: Session) -> OTPResult:
        """
        Verify OTP for EXISTING user - Database storage
        ✅ Keep expired OTPs in database, just mark as unusable
        """
        try:
            otp = otp.strip()
            
            # Get OTP from database
            otp_token = db.query(OTPToken).filter(OTPToken.user_id == user_id).first()
            
            if not otp_token:
                return OTPResult(
                    success=False,
                    message="No OTP found for this user",
                    error_code="OTP_NOT_FOUND"
                )
            
            # ✅ CHECK EXPIRY but don't auto-delete
            time_since_creation = datetime.utcnow() - otp_token.created_at
            if time_since_creation > timedelta(minutes=3):
                return OTPResult(
                    success=False,
                    message="OTP has expired. Please request a new one",
                    error_code="OTP_EXPIRED"
                )
            
            # Verify OTP
            if otp_token.otp == otp:
                # ✅ SUCCESS: Mark as used instead of deleting (Option 1)
                try:
                    otp_token.is_used = True  # Assuming you add this field to your model
                    otp_token.used_at = datetime.utcnow()
                    db.commit()
                    logging.info(f"OTP verified and marked as used for existing user {user_id}")
                    return OTPResult(success=True, message="OTP verified successfully")
                except SQLAlchemyError as db_error:
                    db.rollback()
                    logging.error(f"Failed to mark OTP as used for user {user_id}: {str(db_error)}")
                    # Even if marking fails, verification was successful
                    return OTPResult(success=True, message="OTP verified successfully")
            else:
                return OTPResult(
                    success=False,
                    message="Invalid OTP",
                    error_code="INVALID_OTP"
                )
                
        except Exception as e:
            logging.error(f"Error in verify_otp for user {user_id}: {str(e)}")
            return OTPResult(
                success=False,
                message="Verification failed",
                error_code="UNEXPECTED_ERROR"
            )

    def verify_otp_for_new_user_and_transfer_to_db(self, email: str, otp: str, user_id: uuid.UUID, invite_id: str, db: Session) -> OTPResult:
        """
        ✅ EXACT FLOW: Verify OTP for new user + MOVE to database + mark invite as used
        
        This is called AFTER user creation but BEFORE final login
        """
        try:
            otp = otp.strip()
            email = email.lower()
            
            # Step 1: Verify OTP from memory
            if email not in new_user_otps:
                return OTPResult(
                    success=False,
                    message="No OTP found for this email",
                    error_code="OTP_NOT_FOUND"
                )
            
            stored_otp_data = new_user_otps[email]
            
            # Check expiry
            time_since_creation = datetime.utcnow() - stored_otp_data['created_at']
            if time_since_creation > timedelta(minutes=3):
                return OTPResult(
                    success=False,
                    message="OTP has expired. Please request a new one",
                    error_code="OTP_EXPIRED"
                )
            
            # Verify OTP
            if stored_otp_data['otp'] != otp:
                return OTPResult(
                    success=False,
                    message="Invalid OTP",
                    error_code="INVALID_OTP"
                )
            
            try:
                # ✅ Step 2: MOVE OTP from memory to database
                otp_token = OTPToken(
                    user_id=user_id,
                    otp=stored_otp_data['otp'],
                    created_at=stored_otp_data['created_at']  # Keep original creation time
                )
                db.add(otp_token)
                db.flush()  # Ensure OTP is added before updating invite
                
                # ✅ Step 3: Mark invite code as used
                invite = db.query(InviteCode).filter(InviteCode.invite_id == invite_id).first()
                if invite:
                    invite.is_used = True
                    invite.user_id = user_id
                    invite.used_at = datetime.utcnow()
                else:
                    logging.warning(f"Invite code {invite_id} not found during OTP verification transfer")
                
                # ✅ Step 4: Delete from memory (moved to database)
                del new_user_otps[email]
                
                db.commit()
                
                logging.info(f"OTP verified and moved to database for new user {user_id}, invite {invite_id} marked as used")
                return OTPResult(success=True, message="OTP verified successfully")
                
            except SQLAlchemyError as db_error:
                db.rollback()
                logging.error(f"Database error during OTP transfer for user {user_id}: {str(db_error)}")
                return OTPResult(
                    success=False,
                    message="Failed to complete verification process",
                    error_code="DB_TRANSFER_FAILED"
                )
                
        except Exception as e:
            logging.error(f"Error in verify_otp_for_new_user_and_transfer_to_db for {email}: {str(e)}")
            if email in new_user_otps:
                # Don't delete from memory on unexpected errors, user might retry
                pass
            try:
                db.rollback()
            except:
                pass
            return OTPResult(
                success=False,
                message="Verification failed",
                error_code="UNEXPECTED_ERROR"
            )

    def verify_otp_for_new_user(self, email: str, otp: str, db: Session) -> OTPResult:
        """
        Simple verify for new user (used during registration process)
        """
        try:
            otp = otp.strip()
            email = email.lower()
            
            if email not in new_user_otps:
                return OTPResult(
                    success=False,
                    message="No OTP found for this email",
                    error_code="OTP_NOT_FOUND"
                )
            
            stored_otp_data = new_user_otps[email]
            
            time_since_creation = datetime.utcnow() - stored_otp_data['created_at']
            if time_since_creation > timedelta(minutes=3):
                return OTPResult(
                    success=False,
                    message="OTP has expired. Please request a new one",
                    error_code="OTP_EXPIRED"
                )
            
            # Verify OTP
            if stored_otp_data['otp'] == otp:
                logging.info(f"OTP verified successfully for new user {email}")
                return OTPResult(success=True, message="OTP verified successfully")
            else:
                return OTPResult(
                    success=False,
                    message="Invalid OTP",
                    error_code="INVALID_OTP"
                )
                
        except Exception as e:
            logging.error(f"Error in verify_otp_for_new_user for {email}: {str(e)}")
            return OTPResult(
                success=False,
                message="Verification failed",
                error_code="UNEXPECTED_ERROR"
            )

    def _send_email(self, email: str, otp: str, recipient_name: str) -> bool:
        """Helper method to send email"""
        try:
            payload = {
                "from": {"address": self.from_domain, "name": self.from_name},
                "to": [{"email_address": {"address": email, "name": recipient_name}}],
                "subject": f"Your Sarthi verification code: {otp}",
                "htmlbody": self._get_otp_template(otp, recipient_name)
            }
            
            headers = {
                'accept': "application/json",
                'content-type': "application/json",
                'authorization': self.token,
            }
            
            response = requests.post(self.base_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code in [200, 201]:
                logging.info(f"Email sent successfully to {email}")
                return True
            else:
                logging.error(f"Failed to send email to {email}. Status: {response.status_code}, Response: {response.text}")
                return False
            
        except Exception as e:
            logging.error(f"Error sending email to {email}: {str(e)}")
            return False

    def cleanup_expired_otps(self, db: Session):
        """Clean up very old OTPs from both memory and database"""
        try:
            # Clean up memory OTPs (new users) - only very old ones
            current_time = datetime.utcnow()
            very_old_emails = []
            
            for email, otp_data in new_user_otps.items():
                if current_time - otp_data['created_at'] > timedelta(minutes=10):
                    very_old_emails.append(email)
            
            for email in very_old_emails:
                del new_user_otps[email]
            
            if very_old_emails:
                logging.info(f"Cleaned up {len(very_old_emails)} very old OTPs from memory")
            
            # Clean up database OTPs (existing users) - only very old ones
            try:
                very_old_time = datetime.utcnow() - timedelta(minutes=10)
                expired_count = db.query(OTPToken).filter(
                    OTPToken.created_at < very_old_time
                ).delete()
                db.commit()
                
                if expired_count > 0:
                    logging.info(f"Cleaned up {expired_count} very old OTPs from database")
            except SQLAlchemyError as e:
                logging.error(f"Database error during OTP cleanup: {str(e)}")
                db.rollback()
                
        except Exception as e:
            logging.error(f"Error cleaning up expired OTPs: {str(e)}")

# Global instance
email_service = ZeptoMailService()

def send_email_message(to_email: str, subject: str, message: str, is_html: bool = True, recipient_name: str = "User"):
    """Dummy function for sending general email messages"""
    try:
        logging.info(f"[DUMMY EMAIL] Would send email to: {to_email}")
        logging.info(f"[DUMMY EMAIL] Subject: {subject}")
        logging.info(f"[DUMMY EMAIL] Recipient: {recipient_name}")
        logging.info(f"[DUMMY EMAIL] Message preview: {message[:100]}...")
        logging.info(f"[DUMMY EMAIL] HTML format: {is_html}")
        return True
    except Exception as e:
        logging.error(f"Error in dummy send_email_message: {str(e)}")
        return False