from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import invite, otp, user, reflection, reflection_history

app = FastAPI(
    title="Sarthi API",
    description="Reflection System with Universal Endpoint",
    version="1.0.6"
)

# Enhanced CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,  # Must be False with "*"
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicit methods
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Content-Language",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-CSRFToken",
        "X-Request-ID",
        "Cache-Control",
        "Pragma",
    ],
    expose_headers=["*"],
    max_age=3600,  # Cache preflight for 1 hour
)

# Add explicit OPTIONS handler for all API routes
@app.options("/{full_path:path}")
async def options_handler():
    return {"message": "OK"}

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
        "version": "1.0.6"
    }

@app.get("/", tags=["system"])
def root():
    return {
        "message": "Welcome to Sarthi API",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/test-cors", tags=["system"])
def test_cors():
    return {"message": "CORS test successful", "timestamp": "2025-08-06"}