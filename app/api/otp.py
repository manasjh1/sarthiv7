# app/api/otp.py - UNIFIED FOR EMAIL AND WHATSAPP WITH CONTACT PARAMETER - NOW ASYNC

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
@limiter.limit("3/minute") # Maximum 3 OTP requests per minute per IP
async def send_otp(  # NOW ASYNC
    request: Request, # Required for rate limiting
    otp_request: SendOTPRequest,
    db: Session = Depends(get_db)
):
    try:
        contact = otp_request.contact.strip()

        #Additonal validation
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contact information is required"
            )
        
        result = await auth_manager.send_otp(  # ASYNC CALL
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
@limiter.limit("5/minute")  # Maximum 5 verification attempts per minute per IP
async def verify_otp_and_authenticate(
    request: Request,  # Required for rate limiting
    verify_request: VerifyOTPRequest,
    db: Session = Depends(get_db)
):
    try:
        contact = verify_request.contact.strip()
        otp = verify_request.otp.strip()
        
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
        
        user = auth_manager.utils.find_user_by_contact(contact, db)  
        is_existing_user = user is not None

        if is_existing_user:
            # ===== EXISTING USER VERIFICATION =====
            result = auth_manager.verify_otp(contact, otp, verify_request.invite_token, db)
            if not result.success:
                return VerifyOTPResponse(success=False, message=result.message)
                
            # Convert UUID to string for access token
            user_id_str = str(user.user_id)
            access_token = create_access_token(user_id_str)
            return VerifyOTPResponse(
                success=True,
                access_token=access_token,
                user_id=user_id_str,  # Use string version
                is_new_user=False,
                is_anonymous=user.is_anonymous,
                onboarding_required=user.is_anonymous is None,
                message="Welcome back!"
            )

        else:
            # ===== NEW USER REGISTRATION =====
            if not verify_request.invite_token:
                return VerifyOTPResponse(
                    success=False, 
                    message="Invite token required for new user registration."
                )

            # Verify OTP first
            result = auth_manager.verify_otp(contact, otp, verify_request.invite_token, db)
            if not result.success:
                return VerifyOTPResponse(success=False, message=result.message)

            try:
                # Validate invite token
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

                # Create new user based on contact type
                if "@" in contact:
                    user = User(email=contact.lower(), name="", phone_number=None)
                else:
                    phone_number = int(''.join(filter(str.isdigit, contact)))
                    user = User(email=None, name="", phone_number=phone_number)

                db.add(user)
                db.commit()
                db.refresh(user)

                # Convert UUID to string for safe processing
                user_id_str = str(user.user_id)
                logging.info(f"Created new user with ID: {user_id_str}")

                # Transfer OTP and mark invite as used
                success, message = auth_manager.storage.transfer_to_database(
                    contact=contact, 
                    user_id=user.user_id,  # Pass as UUID for database operations
                    invite_id=str(invite.invite_id),
                    db=db
                )
                
                if not success:
                    # Use string version for logging
                    logging.warning(f"OTP transfer failed for user {user_id_str}: {message}")
                    db.delete(user)
                    db.commit()
                    return VerifyOTPResponse(success=False, message=message)

                # Create access token with string UUIDs
                access_token = create_access_token(user_id_str, str(invite.invite_id))
                return VerifyOTPResponse(
                    success=True,
                    access_token=access_token,
                    user_id=user_id_str,  # Use string version for response
                    is_new_user=True,
                    is_anonymous=user.is_anonymous,
                    onboarding_required=user.is_anonymous is None,
                    message="Account created successfully!"
                )

            except Exception as e:
                db.rollback()
                # Safe logging without UUID serialization issues
                logging.error(f"User creation failed for {contact}: {str(e)}")
                return VerifyOTPResponse(
                    success=False, 
                    message="Error creating account. Please try again."
                )
                
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in verify_otp: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed. Please try again."
        )