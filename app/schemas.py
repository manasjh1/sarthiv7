from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any


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


class InviteValidateRequest(BaseModel):
    invite_code: str

class InviteValidateResponse(BaseModel):
    valid: bool
    message: str
    invite_id: Optional[str] = None
    invite_token: Optional[str] = None 
     


class SendOTPRequest(BaseModel):
    contact: str  
    invite_token: Optional[str] = None  

class SendOTPResponse(BaseModel):
    success: bool
    message: str
    contact_type: Optional[str] = None  


class VerifyOTPRequest(BaseModel):
    contact: str  
    otp: str
    invite_token: Optional[str] = None  

class VerifyOTPResponse(BaseModel):
    success: bool
    message: str
    access_token: Optional[str] = None
    user_id: Optional[str] = None
    is_new_user: Optional[bool] = None
    is_anonymous: Optional[bool] = None 
    onboarding_required: Optional[bool] = None  

class UserProfileResponse(BaseModel):
    user_id: str
    name: Optional[str] = ""
    email: Optional[str] = ""  
    phone_number: Optional[int] = None
    is_verified: Optional[bool] = True
    user_type: Optional[str] = "user"
    proficiency_score: Optional[int] = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class OnboardingChoice(BaseModel):
    is_anonymous: bool
    name: Optional[str] = None