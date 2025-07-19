import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.models import OTPToken, InviteCode
import uuid


new_user_otps: Dict[str, Dict] = {}

class AuthStorage:
    """Handles OTP storage for both existing and new users"""
    
    def store_for_existing_user(self, user_id: uuid.UUID, otp: str, db: Session) -> bool:
        """Store OTP in database for existing user"""
        try:
            
            existing_otp = db.query(OTPToken).filter(OTPToken.user_id == user_id).first()
            if existing_otp:
                time_since_creation = datetime.utcnow() - existing_otp.created_at
                if time_since_creation < timedelta(minutes=1):
                    return False
                
                
                try:
                    db.delete(existing_otp)
                    db.flush()
                    logging.info(f"Deleted old OTP for existing user {user_id}")
                except SQLAlchemyError as e:
                    db.rollback()
                    logging.error(f"Failed to delete old OTP for user {user_id}: {str(e)}")
                    return False
            
            
            try:
                otp_token = OTPToken(
                    user_id=user_id,
                    otp=otp,
                    created_at=datetime.utcnow()
                )
                db.add(otp_token)
                db.commit()
                logging.info(f"OTP stored in database for existing user {user_id}")
                return True
                
            except SQLAlchemyError as db_error:
                db.rollback()
                logging.error(f"Database error storing OTP for user {user_id}: {str(db_error)}")
                return False
                
        except Exception as e:
            logging.error(f"Unexpected error storing OTP for user {user_id}: {str(e)}")
            db.rollback()
            return False
    
    def store_for_new_user(self, email: str, otp: str) -> bool:
        """Store OTP in memory for new user"""
        try:
            email = email.lower()
            
            # Check cooldown - Same as database approach
            if email in new_user_otps:
                time_since_creation = datetime.utcnow() - new_user_otps[email]['created_at']
                if time_since_creation < timedelta(minutes=1):
                    return False
                
                logging.info(f"Replacing old OTP for new user {email}")
            
            # Store in memory
            new_user_otps[email] = {
                'otp': otp,
                'created_at': datetime.utcnow(),
                'email': email
            }
            
            logging.info(f"OTP stored in memory for new user {email}")
            return True
            
        except Exception as e:
            logging.error(f"Error storing OTP in memory for {email}: {str(e)}")
            return False
    
    def verify_for_existing_user(self, user_id: uuid.UUID, otp: str, db: Session) -> Tuple[bool, str]:
        """Verify OTP for existing user"""
        try:
            otp = otp.strip()
            
            # Get OTP from database
            otp_token = db.query(OTPToken).filter(OTPToken.user_id == user_id).first()
            
            if not otp_token:
                return False, "No OTP found for this user"
            
            # Check expiry
            time_since_creation = datetime.utcnow() - otp_token.created_at
            if time_since_creation > timedelta(minutes=3):
                return False, "OTP has expired. Please request a new one"
            
            # Verify OTP
            if otp_token.otp == otp:
                # Delete used OTP
                try:
                    db.delete(otp_token)
                    db.commit()
                    logging.info(f"OTP verified and deleted for existing user {user_id}")
                    return True, "OTP verified successfully"
                except SQLAlchemyError as db_error:
                    db.rollback()
                    logging.error(f"Failed to delete OTP for user {user_id}: {str(db_error)}")
                    return True, "OTP verified successfully"
            else:
                return False, "Invalid OTP"
                
        except Exception as e:
            logging.error(f"Error verifying OTP for user {user_id}: {str(e)}")
            return False, "Verification failed"
    
    def verify_for_new_user(self, email: str, otp: str) -> Tuple[bool, str]:
        """Simple verify for new user (used during registration process)"""
        try:
            otp = otp.strip()
            email = email.lower()
            
            if email not in new_user_otps:
                return False, "No OTP found for this email"
            
            stored_otp_data = new_user_otps[email]
            
            time_since_creation = datetime.utcnow() - stored_otp_data['created_at']
            if time_since_creation > timedelta(minutes=3):
                return False, "OTP has expired. Please request a new one"
            
            # Verify OTP
            if stored_otp_data['otp'] == otp:
                logging.info(f"OTP verified for new user {email}")
                return True, "OTP verified successfully"
            else:
                return False, "Invalid OTP"
                
        except Exception as e:
            logging.error(f"Error verifying OTP for new user {email}: {str(e)}")
            return False, "Verification failed"
    
    def transfer_to_database(self, email: str, user_id: uuid.UUID, invite_id: str, db: Session) -> Tuple[bool, str]:
        """Transfer OTP from memory to database and mark invite as used"""
        try:
            email = email.lower()
            
            # Get OTP from memory
            if email not in new_user_otps:
                return False, "No OTP found for this email"
            
            stored_otp_data = new_user_otps[email]
            
            try:
                # Move OTP from memory to database
                otp_token = OTPToken(
                    user_id=user_id,
                    otp=stored_otp_data['otp'],
                    created_at=stored_otp_data['created_at']
                )
                db.add(otp_token)
                db.flush()
                
                # Mark invite code as used
                invite = db.query(InviteCode).filter(InviteCode.invite_id == invite_id).first()
                if invite:
                    invite.is_used = True
                    invite.user_id = user_id
                    invite.used_at = datetime.utcnow()
                
                # Delete from memory
                del new_user_otps[email]
                
                db.commit()
                
                logging.info(f"OTP transferred to database for user {user_id}, invite {invite_id} marked as used")
                return True, "OTP verified successfully"
                
            except SQLAlchemyError as db_error:
                db.rollback()
                logging.error(f"Database error during OTP transfer for user {user_id}: {str(db_error)}")
                return False, "Failed to complete verification process"
                
        except Exception as e:
            logging.error(f"Error transferring OTP for {email}: {str(e)}")
            try:
                db.rollback()
            except:
                pass
            return False, "Verification failed"
    
    def cleanup_expired_otps(self, db: Session):
        """Clean up very old OTPs from both memory and database"""
        try:
            # Clean up memory OTPs (new users)
            current_time = datetime.utcnow()
            very_old_emails = []
            
            for email, otp_data in new_user_otps.items():
                if current_time - otp_data['created_at'] > timedelta(minutes=10):
                    very_old_emails.append(email)
            
            for email in very_old_emails:
                del new_user_otps[email]
            
            if very_old_emails:
                logging.info(f"Cleaned up {len(very_old_emails)} very old OTPs from memory")
            
            # Clean up database OTPs (existing users)
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
