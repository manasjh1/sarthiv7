from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import UniversalRequest, UniversalResponse
from app.auth import verify_token, create_access_token
from app.stage_handler import StageHandler
from app.models import User
from pydantic import BaseModel
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
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Login schemas
class LoginRequest(BaseModel):
    email: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    message: str

@app.post("/api/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Login endpoint - Generate JWT token for user
    """
    # Find user by email
    user = db.query(User).filter(
        User.email == request.email.lower().strip(),
        User.status == 1
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Generate JWT token
    access_token = create_access_token(str(user.user_id))
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=str(user.user_id),
        message="Login successful"
    )

@app.post("/api/reflection", response_model=UniversalResponse)
def process_reflection(
    request: UniversalRequest,
    user_id: uuid.UUID = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Universal endpoint for handling all reflection stages with new API structure
    
    - **Stage 0**: Initial request (no reflection_id) - creates new reflection and returns categories
    - **Stage 1**: Category selection with data array containing Category_no and Category_name
    - **Stage 2**: Person name input via message field
    - **Stage 3**: Relationship input and completion
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

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Sarthi API",
        "version": "1.0.0"
    }

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Welcome to Sarthi API",
        "docs": "/docs",
        "health": "/health"
    }