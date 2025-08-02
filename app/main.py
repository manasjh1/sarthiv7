from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.api import invite, otp, user, reflection, reflection_history
import logging

# Create limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Sarthi API",
    description="Reflection System with Universal Endpoint",
    version="1.0.0"
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://sarthi-frontend-six.vercel.app",
        "https://app.sarthi.me"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(invite.router)
app.include_router(otp.router)
app.include_router(user.router)
app.include_router(reflection.router)
app.include_router(reflection_history.router)

@app.get("/health", tags=["system"])
def health_check():
    return {
        "status": "healthy",
        "service": "Sarthi API",
        "version": "1.0.0"
    }

@app.get("/", tags=["system"])
def root():
    return {
        "message": "Welcome to Sarthi API",
        "docs": "/docs",
        "health": "/health"
    }

@app.on_event("startup")
async def startup_event():
    """Startup tasks"""
    logging.info("Sarthi API started successfully")