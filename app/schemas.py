from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any

# Existing schemas
class UniversalRequest(BaseModel):
    reflection_id: Optional[str] = None
    message: str
    data: List[Dict[str, Any]] = []

class ProgressInfo(BaseModel):
    current_step: int
    total_step: int
    workflow_completed: bool

class UniversalResponse(BaseModel):
    success: bool
    reflection_id: str
    sarthi_message: str
    current_stage: int
    next_stage: int
    progress: ProgressInfo
    data: List[Dict[str, Any]] = []

# Auth-related schemas
class InviteValidateRequest(BaseModel):
    invite_code: str

class InviteValidateResponse(BaseModel):
    valid: bool
    message: str
    invite_id: Optional[str] = None
    invite_token: Optional[str] = None  # NEW: JWT token for registration

class VerifyOTPRequest(BaseModel):
    contact: str  # Email or phone number
    otp: str
    invite_token: Optional[str] = None  # NEW: JWT token from invite validation

class VerifyOTPResponse(BaseModel):
    success: bool
    access_token: Optional[str] = None
    user_id: Optional[str] = None
    is_new_user: Optional[bool] = None
    message: str

# Login schemas (already in your main.py)
class LoginRequest(BaseModel):
    email: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    message: str

# User profile response
class UserProfileResponse(BaseModel):
    user_id: str
    name: Optional[str] = ""
    email: Optional[str] = ""  
    phone_number: Optional[int] = None  # Allow None, don't default to 0
    is_verified: Optional[bool] = True
    user_type: Optional[str] = "user"
    proficiency_score: Optional[int] = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None