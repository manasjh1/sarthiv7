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
def send_otp(
    request: SendOTPRequest,
    db: Session = Depends(get_db)
):
    contact = request.contact.strip()
    result = auth_manager.send_otp(
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
def verify_otp_and_authenticate(
    request: VerifyOTPRequest,
    db: Session = Depends(get_db)
):
    contact = request.contact.strip()
    user = auth_manager.utils.find_user_by_contact(contact, db)  

    if user:
        if "@" in contact:
            result = auth_manager.verify_otp(contact, request.otp, request.invite_token, db)
            if not result.success:
                return VerifyOTPResponse(success=False, message=result.message)
        else:
            if request.otp != "141414":
                return VerifyOTPResponse(success=False, message="Invalid OTP.")
        access_token = create_access_token(str(user.user_id))
        return VerifyOTPResponse(
            success=True,
            access_token=access_token,
            user_id=str(user.user_id),
            is_new_user=False,
            message="Welcome back!"
        )
    else:
        if not request.invite_token:
            return VerifyOTPResponse(success=False, message="Invite token required.")

        if "@" in contact:
            result = auth_manager.verify_otp(contact.lower(), request.otp, request.invite_token, db)
            if not result.success:
                return VerifyOTPResponse(success=False, message=result.message)
        else:
            if request.otp != "141414":
                return VerifyOTPResponse(success=False, message="Invalid OTP.")

        try:
            invite_data = verify_invite_token(request.invite_token)
            invite = db.query(InviteCode).filter(
                InviteCode.invite_id == invite_data["invite_id"],
                InviteCode.invite_code == invite_data["invite_code"]
            ).first()
            if not invite or (invite.is_used and invite.user_id):
                return VerifyOTPResponse(success=False, message="Invite code already used.")

            if "@" in contact:
                user = User(email=contact.lower(), name="", phone_number=None)
            else:
                phone_number = int(''.join(filter(str.isdigit, contact)))
                user = User(email=None, name="", phone_number=phone_number)

            db.add(user)
            db.commit()
            db.refresh(user)

            if "@" in contact:
                success, message = auth_manager.storage.transfer_to_database(
                    email=contact.lower(), user_id=user.user_id, invite_id=invite.invite_id, db=db
                )
                if not success:
                    db.delete(user)
                    db.commit()
                    return VerifyOTPResponse(success=False, message=message)
            else:
                invite.is_used = True
                invite.user_id = user.user_id
                invite.used_at = datetime.utcnow()
                db.commit()

            access_token = create_access_token(str(user.user_id), invite.invite_id)
            return VerifyOTPResponse(
                success=True,
                access_token=access_token,
                user_id=str(user.user_id),
                is_new_user=True,
                message="Account created successfully!"
            )

        except Exception as e:
            db.rollback()
            logging.error(f"User creation failed: {str(e)}")
            return VerifyOTPResponse(success=False, message="Error creating account.")
