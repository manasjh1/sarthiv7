from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, OTPToken
from app.schemas import OnboardingChoice
from app.auth import get_current_user
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import logging
from services.auth.manager import AuthManager

router = APIRouter(prefix="/api/user", tags=["user"])
auth_manager = AuthManager()
logger = logging.getLogger(__name__)


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    
class RequestContactOTPRequest(BaseModel):
    contact: str  
    contact_type: Optional[str] = None  

class VerifyContactOTPRequest(BaseModel):
    contact: str
    otp: str
    contact_type: Optional[str] = None

class UpdateProfileResponse(BaseModel):
    success: bool
    message: str
    user: Optional[dict] = None

@router.get("/me")
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return {
        "user_id": str(current_user.user_id),
        "email": current_user.email,
        "phone": current_user.phone_number,
        "name": current_user.name,
        "is_anonymous": current_user.is_anonymous,
        "is_verified": current_user.is_verified,
        "has_email": current_user.email is not None,
        "has_phone": current_user.phone_number is not None
    }

@router.put("/update-name", response_model=UpdateProfileResponse)
async def update_user_name(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user's name - no OTP required"""
    try:
        if not request.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name is required"
            )
        
        name = request.name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name cannot be empty"
            )
        
        if len(name) > 256:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name is too long (max 256 characters)"
            )
        
        current_user.name = name
        current_user.updated_at = datetime.utcnow()
        
        if current_user.is_anonymous:
            current_user.is_anonymous = False
            logger.info(f"User {current_user.user_id} is no longer anonymous after updating name")
        
        db.commit()
        db.refresh(current_user)
        
        return UpdateProfileResponse(
            success=True,
            message="Name updated successfully",
            user={
                "user_id": str(current_user.user_id),
                "name": current_user.name,
                "email": current_user.email,
                "phone": current_user.phone_number,
                "is_anonymous": current_user.is_anonymous
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating name for user {current_user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update name"
        )

@router.post("/request-contact-otp")
async def request_contact_otp(
    request: RequestContactOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Request OTP for adding a new email or phone number to profile"""
    try:
        contact = request.contact.strip()
        
        contact_type = request.contact_type
        if not contact_type:
            contact_type = auth_manager.utils.detect_channel(contact)
        
        normalized_contact = auth_manager.utils.normalize_contact(contact, contact_type)
        
        logger.info(f"User {current_user.user_id} requesting OTP to add {contact_type}: {normalized_contact}")
        
        if contact_type == "email" and current_user.email:
            if current_user.email.lower() == normalized_contact.lower():
                return {
                    "success": False,
                    "message": "This email is already linked to your account"
                }
            else:
                logger.info(f"User {current_user.user_id} wants to change email from {current_user.email} to {normalized_contact}")
        
        if contact_type == "whatsapp" and current_user.phone_number:
            clean_phone = auth_manager.utils.normalize_contact(str(current_user.phone_number), "whatsapp")
            if clean_phone == normalized_contact:
                return {
                    "success": False,
                    "message": "This phone number is already linked to your account"
                }
            else:
                logger.info(f"User {current_user.user_id} wants to change phone from {current_user.phone_number} to {normalized_contact}")
        
        existing_user = auth_manager.utils.find_user_by_contact(normalized_contact, db)
        if existing_user and existing_user.user_id != current_user.user_id:
            return {
                "success": False,
                "message": f"This {contact_type} is already registered with another account"
            }
        
        
        otp = auth_manager._generate_otp()
        
        success = auth_manager.storage.store_for_existing_user(current_user.user_id, otp, db)
        if not success:
            return {
                "success": False,
                "message": "Please wait 60 seconds before requesting a new OTP"
            }
        
        
        if contact_type == "email":
            template_data = {
                "otp": otp,
                "name": current_user.name or "User",
                "app_name": "Sarthi"
            }
            content = auth_manager._load_template("otp_email.html", template_data)
            metadata = {
                "subject": f"Verify your new email address - OTP: {otp}",
                "recipient_name": current_user.name or "User"
            }
            result = await auth_manager.email_provider.send(normalized_contact, content, metadata)
        else:  
            result = await auth_manager.whatsapp_provider.send(normalized_contact, otp)
        
        if not result.success:
            return {
                "success": False,
                "message": f"Failed to send OTP: {result.error}"
            }
        
        return {
            "success": True,
            "message": f"OTP sent successfully to {contact}",
            "contact_type": contact_type
        }
        
    except Exception as e:
        logger.error(f"Error requesting contact OTP: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP"
        )


@router.post("/verify-contact-otp", response_model=UpdateProfileResponse)
async def verify_contact_otp_and_update(
    request: VerifyContactOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verify OTP and add/update contact (email or phone)"""
    try:
        contact = request.contact.strip()
        otp = request.otp.strip()
        
        # Validate OTP format
        if len(otp) != 6 or not otp.isdigit():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP must be a 6-digit number"
            )
        
        # Detect and normalize contact
        contact_type = request.contact_type
        if not contact_type:
            contact_type = auth_manager.utils.detect_channel(contact)
        
        normalized_contact = auth_manager.utils.normalize_contact(contact, contact_type)
        
        logger.info(f"User {current_user.user_id} verifying OTP for {contact_type}: {normalized_contact}")
        
        # Verify OTP
        success, message = auth_manager.storage.verify_for_existing_user(
            current_user.user_id, otp, db
        )
        
        if not success:
            return UpdateProfileResponse(
                success=False,
                message=message
            )
        
        # Check again if contact is used by another user
        existing_user = auth_manager.utils.find_user_by_contact(normalized_contact, db)
        if existing_user and existing_user.user_id != current_user.user_id:
            return UpdateProfileResponse(
                success=False,
                message=f"This {contact_type} is already registered with another account"
            )
        
        # Update user's contact
        if contact_type == "email":
            old_email = current_user.email
            current_user.email = normalized_contact
            logger.info(f"User {current_user.user_id} updated email from {old_email} to {normalized_contact}")
        else:  # whatsapp/phone
            old_phone = current_user.phone_number
            # Convert normalized phone string to integer
            phone_number = int(normalized_contact) if normalized_contact.isdigit() else None
            if not phone_number:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid phone number format"
                )
            current_user.phone_number = phone_number
            logger.info(f"User {current_user.user_id} updated phone from {old_phone} to {phone_number}")
        
        current_user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(current_user)
        
        return UpdateProfileResponse(
            success=True,
            message=f"{contact_type.capitalize()} updated successfully",
            user={
                "user_id": str(current_user.user_id),
                "name": current_user.name,
                "email": current_user.email,
                "phone": current_user.phone_number,
                "is_anonymous": current_user.is_anonymous,
                "has_email": current_user.email is not None,
                "has_phone": current_user.phone_number is not None
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error verifying contact OTP: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update contact"
        )

@router.post("/onboarding")
async def set_onboarding_choice(
    data: OnboardingChoice,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if data.is_anonymous:
        current_user.name = None
        current_user.is_anonymous = True
    else:
        if not data.name:
            raise HTTPException(status_code=400, detail="Name is required for non-anonymous users.")
        current_user.name = data.name.strip()
        current_user.is_anonymous = False

    db.commit()
    return {"message": "Onboarding information saved successfully."}