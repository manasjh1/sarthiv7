from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import invite, otp, user, reflection, reflection_history

app = FastAPI(
    title="Sarthi API",
    description="Reflection System with Universal Endpoint",
    version="1.0.7"  # Updated version
)

# Secure CORS Configuration - matches Cloudflare rules
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sarthi-frontend-seven.vercel.app",  # Production frontend 
        "http://localhost:3000",                     # Local development
        "https://localhost:3000",                    # HTTPS local development
    ],
    allow_credentials=True,  # Matches Cloudflare setting
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type", 
        "Authorization", 
        "X-Requested-With",
        "Accept",
        "Accept-Language",
        "Cache-Control",
    ],
    max_age=3600,  # Matches Cloudflare setting
)

# Remove the OPTIONS handler - Cloudflare handles it now
# @app.options("/{full_path:path}") - DELETE THIS

# Rest of your code stays the same...
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
        "version": "1.0.7"
    }

@app.get("/", tags=["system"])
def root():
    return {
        "message": "Welcome to Sarthi API",
        "docs": "/docs",
        "health": "/health"
    }