# app/api/otp.py - UNIFIED FOR EMAIL AND WHATSAPP WITH CONTACT PARAMETER - NOW ASYNC

from fastapi import APIRouter, Depends
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

@router.post("/send-otp", response_model=SendOTPResponse)
async def send_otp(  # NOW ASYNC
    request: SendOTPRequest,
    db: Session = Depends(get_db)
):
    contact = request.contact.strip()
    result = await auth_manager.send_otp(  # ASYNC CALL
        contact=contact,
        invite_token=request.invite_token,
        db=db
    )
    return SendOTPResponse(
        success=result.success,
        message=result.message,
        contact_type=result.contact_type
    )

@router.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_otp_and_authenticate(  # NOW ASYNC
    request: VerifyOTPRequest,
    db: Session = Depends(get_db)
):
    contact = request.contact.strip()
    user = auth_manager.utils.find_user_by_contact(contact, db)  

    if user:
        # ===== EXISTING USER VERIFICATION (UNIFIED FOR EMAIL AND WHATSAPP) =====
        result = auth_manager.verify_otp(contact, request.otp, request.invite_token, db)
        if not result.success:
            return VerifyOTPResponse(success=False, message=result.message)
            
        access_token = create_access_token(str(user.user_id))
        return VerifyOTPResponse(
            success=True,
            access_token=access_token,
            user_id=str(user.user_id),
            is_new_user=False,
            is_anonymous=user.is_anonymous,
            onboarding_required=user.is_anonymous is None,
            message="Welcome back!"
        )

    else:
        # ===== NEW USER REGISTRATION (UNIFIED FOR EMAIL AND WHATSAPP) =====
        if not request.invite_token:
            return VerifyOTPResponse(success=False, message="Invite token required.")

        # Use auth manager for OTP verification (both email and WhatsApp)
        result = auth_manager.verify_otp(contact, request.otp, request.invite_token, db)
        if not result.success:
            return VerifyOTPResponse(success=False, message=result.message)

        try:
            invite_data = verify_invite_token(request.invite_token)
            invite = db.query(InviteCode).filter(
                InviteCode.invite_id == invite_data["invite_id"],
                InviteCode.invite_code == invite_data["invite_code"]
            ).first()
            if not invite or (invite.is_used and invite.user_id):
                return VerifyOTPResponse(success=False, message="Invite code already used.")

            # Create new user based on contact type (email or phone)
            if "@" in contact:
                user = User(email=contact.lower(), name="", phone_number=None)
            else:
                phone_number = int(''.join(filter(str.isdigit, contact)))
                user = User(email=None, name="", phone_number=phone_number)

            db.add(user)
            db.commit()
            db.refresh(user)

            # Transfer OTP and mark invite as used (UNIFIED FOR BOTH EMAIL AND WHATSAPP)
            success, message = auth_manager.storage.transfer_to_database(
                contact=contact, user_id=user.user_id, invite_id=invite.invite_id, db=db
            )
            if not success:
                db.delete(user)
                db.commit()
                return VerifyOTPResponse(success=False, message=message)

            access_token = create_access_token(str(user.user_id), invite.invite_id)
            return VerifyOTPResponse(
                success=True,
                access_token=access_token,
                user_id=str(user.user_id),
                is_new_user=True,
                is_anonymous=user.is_anonymous,  # Should be None at this point
                onboarding_required=user.is_anonymous is None,
                message="Account created successfully!"
            )

        except Exception as e:
            db.rollback()
            logging.error(f"User creation failed: {str(e)}")
            return VerifyOTPResponse(success=False, message="Error creating account.")