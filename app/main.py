from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import invite, otp, user, reflection, reflection_history

app = FastAPI(
    title="Sarthi API",
    description="Reflection System with Universal Endpoint",
    version="1.0.3"  # Updated version
)

# CORS Configuration - Fixed for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://localhost:3000",  # HTTPS local development
        "https://127.0.0.1:3000",  # HTTPS local development
        "https://sarthi-frontend-six.vercel.app",
        "https://sarthi-frontend-six.vercel.app/",  # With trailing slash
        "*"  # Allow all origins - REMOVE THIS IN PRODUCTION
    ],
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

# Include all routers
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
        "version": "1.0.3"  # Updated to match FastAPI version
    }

@app.get("/", tags=["system"])
def root():
    return {
        "message": "Welcome to Sarthi API",
        "docs": "/docs",
        "health": "/health"
    }