from fastapi import APIRouter, Depends, Request, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import SendOTPRequest, SendOTPResponse, VerifyOTPRequest, VerifyOTPResponse
from app.auth import create_access_token
from app.models import User, InviteCode
from .invite import verify_invite_token
from datetime import datetime
import logging

from services.auth.manager import AuthManager

router = APIRouter(prefix="/api/auth", tags=["auth"])
auth_manager = AuthManager()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

@router.post("/send-otp", response_model=SendOTPResponse)
@limiter.limit("3/minute")
async def send_otp(
    request: Request,
    otp_request: SendOTPRequest,
    db: Session = Depends(get_db)
):
    try:
        contact = otp_request.contact.strip()
        
        # Additional validation
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contact information is required"
            )
        
        logging.info(f"🔍 OTP Request - Contact: {contact}, Has invite token: {bool(otp_request.invite_token)}")
        
        result = await auth_manager.send_otp(
            contact=contact,
            invite_token=otp_request.invite_token,
            db=db
        )
        
        return SendOTPResponse(
            success=result.success,
            message=result.message,
            contact_type=result.contact_type
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in send_otp: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP. Please try again later."
        )

@router.post("/verify-otp", response_model=VerifyOTPResponse)
@limiter.limit("5/minute")
async def verify_otp_and_authenticate(
    request: Request,
    verify_request: VerifyOTPRequest,
    db: Session = Depends(get_db)
):
    try:
        contact = verify_request.contact.strip()
        otp = verify_request.otp.strip()
        
        # Log the incoming request for debugging
        logging.info(f"🔍 OTP Verification - Contact: {contact}, OTP: {otp}, Has invite token: {bool(verify_request.invite_token)}")
        
        # Additional validation
        if not contact or not otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contact and OTP are required"
            )
        
        if len(otp) != 6 or not otp.isdigit():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP must be a 6-digit number"
            )
        
        # Use normalized contact for user lookup
        user = auth_manager.utils.find_user_by_contact(contact, db)
        is_existing_user = user is not None
        
        logging.info(f"🔍 User Check - Is Existing: {is_existing_user}")

        if is_existing_user:
            # ===== EXISTING USER VERIFICATION =====
            logging.info(f"🔍 Processing existing user verification")
            
            result = auth_manager.verify_otp(contact, otp, verify_request.invite_token, db)
            if not result.success:
                logging.warning(f"🔍 Existing user OTP verification failed: {result.message}")
                return VerifyOTPResponse(success=False, message=result.message)
                
            # Convert UUID to string for access token - SAFE CONVERSION
            try:
                user_id_str = str(user.user_id)
                logging.info(f"🔍 Creating access token for existing user: {user_id_str}")
            except Exception as e:
                logging.error(f"Error converting user_id to string: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authentication error"
                )
                
            access_token = create_access_token(user_id_str)
            return VerifyOTPResponse(
                success=True,
                access_token=access_token,
                user_id=user_id_str,
                is_new_user=False,
                is_anonymous=user.is_anonymous,
                onboarding_required=user.is_anonymous is None,
                message="Welcome back!"
            )

        else:
            # ===== NEW USER REGISTRATION =====
            logging.info(f"🔍 Processing new user registration")
            
            if not verify_request.invite_token:
                return VerifyOTPResponse(
                    success=False, 
                    message="Invite token required for new user registration."
                )

            # Verify OTP first using normalized contact
            logging.info(f"🔍 Verifying OTP for new user")
            result = auth_manager.verify_otp(contact, otp, verify_request.invite_token, db)
            if not result.success:
                logging.warning(f"🔍 New user OTP verification failed: {result.message}")
                return VerifyOTPResponse(success=False, message=result.message)

            try:
                # Validate invite token
                logging.info(f"🔍 Validating invite token")
                invite_data = verify_invite_token(verify_request.invite_token)
                invite = db.query(InviteCode).filter(
                    InviteCode.invite_id == invite_data["invite_id"],
                    InviteCode.invite_code == invite_data["invite_code"]
                ).first()
                
                if not invite or (invite.is_used and invite.user_id):
                    return VerifyOTPResponse(
                        success=False, 
                        message="Invite code has already been used."
                    )

                # Create new user based on contact type - use NORMALIZED contact
                logging.info(f"🔍 Creating new user for contact: {contact}")
                normalized_contact = auth_manager.utils.normalize_contact_auto(contact)
                
                if "@" in normalized_contact:
                    user = User(email=normalized_contact, name="", phone_number=None)
                else:
                    phone_number = int(normalized_contact) if normalized_contact.isdigit() else None
                    user = User(email=None, name="", phone_number=phone_number)

                db.add(user)
                db.commit()
                db.refresh(user)

                # Convert UUID to string for safe processing
                try:
                    user_id_str = str(user.user_id)
                    logging.info(f"🔍 Created new user with ID: {user_id_str}")
                except Exception as e:
                    logging.error(f"Error converting new user_id to string: {e}")
                    db.delete(user)
                    db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Account creation error"
                    )

                # Transfer OTP and mark invite as used - use NORMALIZED contact
                logging.info(f"🔍 Transferring OTP to database for user {user_id_str}")
                success, message = auth_manager.storage.transfer_to_database(
                    contact=normalized_contact,  # Use normalized contact consistently
                    user_id=user.user_id,
                    invite_id=str(invite.invite_id),
                    db=db
                )
                
                if not success:
                    logging.warning(f"🔍 OTP transfer failed for user {user_id_str}: {message}")
                    db.delete(user)
                    db.commit()
                    return VerifyOTPResponse(success=False, message=message)

                # Create access token with string UUIDs
                try:
                    invite_id_str = str(invite.invite_id)
                    access_token = create_access_token(user_id_str, invite_id_str)
                    logging.info(f"🔍 Access token created successfully for user {user_id_str}")
                except Exception as e:
                    logging.error(f"Error creating access token: {e}")
                    db.delete(user)
                    db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Token creation error"
                    )
                    
                return VerifyOTPResponse(
                    success=True,
                    access_token=access_token,
                    user_id=user_id_str,
                    is_new_user=True,
                    is_anonymous=user.is_anonymous,
                    onboarding_required=user.is_anonymous is None,
                    message="Account created successfully!"
                )

            except HTTPException:
                raise
            except Exception as e:
                db.rollback()
                logging.error(f"🔍 User creation failed for {contact}: {str(e)}")
                return VerifyOTPResponse(
                    success=False, 
                    message="Error creating account. Please try again."
                )
                
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"🔍 Unexpected error in verify_otp: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed. Please try again."
        )
