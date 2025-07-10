from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.schemas import (
    UniversalRequest, 
    UniversalResponse,
    InviteValidateRequest,
    InviteValidateResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
    UserProfileResponse
)
from app.auth import verify_token, create_access_token, get_current_user
from app.config import settings
from app.stage_handler import StageHandler
from app.models import User, InviteCode
from datetime import datetime, timedelta
from jose import JWTError, jwt
import logging
import uuid

# Create FastAPI application
app = FastAPI(
    title="Sarthi API",
    description="Reflection System with Universal Endpoint",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://v0-app-sarthi-me.vercel.app"  # Add your deployed frontend URL
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)    

def find_user_by_contact(contact: str, db: Session):
    """Helper function to find user by email or phone with flexible matching"""
    contact = contact.strip()
    user = None
    
    if "@" in contact:
        # Email lookup
        user = db.query(User).filter(
            User.email == contact.lower(),
            User.status == 1
        ).first()
    else:
        # Phone lookup with flexible matching
        clean_contact = ''.join(filter(str.isdigit, contact))
        if clean_contact:
            try:
                # Try exact match first
                phone_number = int(clean_contact)
                user = db.query(User).filter(
                    User.phone_number == phone_number,
                    User.status == 1
                ).first()
                
                # Try without country code
                if not user and len(clean_contact) > 10:
                    local_number = int(clean_contact[-10:])
                    user = db.query(User).filter(
                        User.phone_number == local_number,
                        User.status == 1
                    ).first()
                
                # Try with common country codes
                if not user and len(clean_contact) == 10:
                    for country_code in ['1', '91']:  # US, India
                        full_number = int(country_code + clean_contact)
                        user = db.query(User).filter(
                            User.phone_number == full_number,
                            User.status == 1
                        ).first()
                        if user:
                            break
            except ValueError:
                pass
    
    return user

# Helper functions for invite JWT
def create_invite_token(invite_id: str, invite_code: str) -> str:
    """Create JWT token for invite validation"""
    expire = datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry for invite tokens
    to_encode = {
        "invite_id": invite_id,
        "invite_code": invite_code,
        "type": "invite",
        "exp": expire,
        "iat": datetime.utcnow()
    }
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

def verify_invite_token(token: str) -> dict:
    """Verify invite JWT token"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        
        if payload.get("type") != "invite":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        return {
            "invite_id": payload.get("invite_id"),
            "invite_code": payload.get("invite_code")
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired invite token")

@app.post("/api/invite/validate", response_model=InviteValidateResponse, tags=["auth"])
def validate_invite_code(
    request: InviteValidateRequest,
    db: Session = Depends(get_db)
):
    """
    Validate invite code and generate JWT with invite_id
    This JWT will be used for new user registration
    """
    invite_code = request.invite_code.strip().upper()
    logging.info(f"Validating invite code: {invite_code}")
    
    # Check if invite code exists and is available
    existing_invite = db.query(InviteCode).filter(
        InviteCode.invite_code == invite_code
    ).first()
    
    if not existing_invite:
        logging.error(f"Invite code {invite_code} does not exist in database")
        return InviteValidateResponse(
            valid=False,
            message=f"Invite code '{invite_code}' does not exist. Please check your code and try again."
        )
    
    # Check if already used
    if existing_invite.is_used and existing_invite.user_id:
        logging.error(f"Invite code {invite_code} already used by user {existing_invite.user_id}")
        return InviteValidateResponse(
            valid=False,
            message=f"Invite code '{invite_code}' has already been used by another user. Each invite code can only be used once."
        )
    
    # Generate JWT token with invite_id for registration
    invite_jwt = create_invite_token(str(existing_invite.invite_id), invite_code)
    logging.info(f"Generated invite JWT for {invite_code}")
    
    return InviteValidateResponse(
        valid=True,
        message=f"Invite code '{invite_code}' is valid! You can now proceed with registration.",
        invite_id=str(existing_invite.invite_id),
        invite_token=invite_jwt  # JWT for registration
    )

@app.post("/api/auth/verify-otp", response_model=VerifyOTPResponse, tags=["auth"])
def verify_otp_and_authenticate(
    request: VerifyOTPRequest,
    db: Session = Depends(get_db)
):
    """
    Smart OTP verification:
    - If user exists: Login directly 
    - If user doesn't exist: Require invite token to create account
    """
    contact = request.contact.strip()
    
    logging.info(f"OTP Verification - Contact: {contact}, OTP: {request.otp}, Invite token provided: {bool(request.invite_token)}")
    
    # Verify OTP first
    if request.otp != "141414":
        logging.error(f"Invalid OTP provided: {request.otp}")
        return VerifyOTPResponse(
            success=False,
            message=f"Invalid OTP '{request.otp}'. Please enter the correct 6-digit code. (Development OTP: 141414)"
        )
    
    # Check if user exists
    user = find_user_by_contact(contact, db)
    
    if user:
        # USER EXISTS - Login directly
        logging.info(f"Existing user login: {user.user_id}")
        access_token = create_access_token(str(user.user_id))
        
        return VerifyOTPResponse(
            success=True,
            access_token=access_token,
            user_id=str(user.user_id),
            is_new_user=False,
            message="Welcome back! You have been logged in successfully."
        )
    else:
        # USER DOESN'T EXIST - Need invite token to create account
        if not request.invite_token:
            logging.error(f"New user {contact} attempted registration without invite token")
            return VerifyOTPResponse(
                success=False,
                message="User not found. New user registration requires a valid invite code. Please validate your invite code first."
            )
        
        # Verify invite token
        try:
            invite_data = verify_invite_token(request.invite_token)
            invite_id = invite_data["invite_id"]
            invite_code = invite_data["invite_code"]
            logging.info(f"Valid invite token for invite_id: {invite_id}, code: {invite_code}")
        except HTTPException as e:
            logging.error(f"Invalid invite token: {e.detail}")
            return VerifyOTPResponse(
                success=False,
                message="Invalid or expired invite token. Please validate your invite code again."
            )
        
        # Get invite from database
        invite = db.query(InviteCode).filter(
            InviteCode.invite_id == invite_id,
            InviteCode.invite_code == invite_code
        ).first()
        
        if not invite:
            logging.error(f"Invite not found in database: {invite_id}")
            return VerifyOTPResponse(
                success=False,
                message="Invite code not found. Please validate your invite code again."
            )
        
        if invite.is_used and invite.user_id:
            logging.error(f"Invite {invite_code} already used by user {invite.user_id}")
            return VerifyOTPResponse(
                success=False,
                message=f"Invite code '{invite_code}' has already been used by another user."
            )
        
        # CREATE NEW USER
        try:
            if "@" in contact:
                # Email-based signup
                logging.info(f"Creating new user with email: {contact}")
                user = User(
                    email=contact.lower(),
                    name="",
                    phone_number=None
                )
            else:
                # Phone-based signup
                clean_contact = ''.join(filter(str.isdigit, contact))
                if not clean_contact:
                    return VerifyOTPResponse(
                        success=False,
                        message=f"Invalid phone number format: '{contact}'"
                    )
                
                phone_number = int(clean_contact)
                logging.info(f"Creating new user with phone: {phone_number}")
                user = User(
                    phone_number=phone_number,
                    email=None,
                    name=""
                )
            
            db.add(user)
            db.commit()
            db.refresh(user)
            logging.info(f"New user created: {user.user_id}")
            
            # Mark invite as used and link to user
            invite.is_used = True
            invite.user_id = user.user_id
            invite.used_at = datetime.utcnow()
            db.commit()
            logging.info(f"Invite {invite_code} linked to user {user.user_id}")
            
            # Generate user JWT token
            access_token = create_access_token(str(user.user_id), invite_id)
            
            return VerifyOTPResponse(
                success=True,
                access_token=access_token,
                user_id=str(user.user_id),
                is_new_user=True,
                message="Account created successfully! Welcome to Sarthi."
            )
            
        except Exception as e:
            logging.error(f"Error creating user: {str(e)}")
            db.rollback()
            return VerifyOTPResponse(
                success=False,
                message=f"Failed to create account. Please try again or contact support."
            )

@app.get("/api/user/me", response_model=UserProfileResponse, tags=["user"])
def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information"""
    logging.info(f"Getting user info for user_id: {current_user.user_id}")
    logging.info(f"User data: phone={current_user.phone_number}, email={current_user.email}, name={current_user.name}")
    
    return UserProfileResponse(
        user_id=str(current_user.user_id),
        name=current_user.name or "",  # Handle None values
        email=current_user.email or "",  # Handle None values
        phone_number=current_user.phone_number or 0,  # Handle None values
        is_verified=getattr(current_user, 'is_verified', True),
        user_type=current_user.user_type,
        proficiency_score=current_user.proficiency_score,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
        updated_at=current_user.updated_at.isoformat() if current_user.updated_at else None
    )

@app.post("/api/reflection", response_model=UniversalResponse, tags=["reflection"])
def process_reflection(
    request: UniversalRequest,
    user_id: uuid.UUID = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Universal endpoint for handling all reflection stages
    """
    try:
        handler = StageHandler(db)
        response = handler.process_request(request, user_id)
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post("/api/invite/reset/{invite_code}", tags=["admin"])
def reset_invite_code(
    invite_code: str,
    db: Session = Depends(get_db)
):
    """
    Reset an invite code for testing purposes
    WARNING: This is for development only - remove in production
    """
    invite_code = invite_code.strip().upper()
    
    invite = db.query(InviteCode).filter(
        InviteCode.invite_code == invite_code
    ).first()
    
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invite code '{invite_code}' not found"
        )
    
    old_user_id = invite.user_id
    
    # Reset invite code (don't delete user, just unlink)
    invite.is_used = False
    invite.user_id = None
    invite.used_at = None
    
    db.commit()
    
    return {
        "success": True,
        "message": f"Invite code '{invite_code}' has been reset and is now available for use",
        "previous_user_id": str(old_user_id) if old_user_id else None
    }

@app.get("/api/invite/status", tags=["admin"])
def get_invite_codes_status(db: Session = Depends(get_db)):
    """
    Get status of all invite codes for debugging
    WARNING: This is for development only - remove in production
    """
    invites = db.query(InviteCode).all()
    
    result = []
    for invite in invites:
        status = "AVAILABLE"
        if invite.is_used and invite.user_id:
            status = "USED"
        elif invite.is_used and not invite.user_id:
            status = "RESERVED"
        
        result.append({
            "invite_code": invite.invite_code,
            "status": status,
            "is_used": invite.is_used,
            "user_id": str(invite.user_id) if invite.user_id else None,
            "used_at": invite.used_at.isoformat() if invite.used_at else None
        })
    
    return {
        "invite_codes": result,
        "available_codes": [r["invite_code"] for r in result if r["status"] == "AVAILABLE"]
    }

@app.get("/health", tags=["system"])
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Sarthi API",
        "version": "1.0.0"
    }

@app.get("/", tags=["system"])
def root():
    """Root endpoint"""
    return {
        "message": "Welcome to Sarthi API",
        "docs": "/docs",
        "health": "/health"
    }