from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import invite, otp, user, reflection, reflection_history
import app.api.invite_generate as invite_generate
import app.api.reflection_inbox_outbox as reflection_inbox_outbox


app = FastAPI(
    title="Sarthi API",
    description="Reflection System with Universal Endpoint",
    version="1.0.10"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.sarthi.me"      
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(invite_generate.router)
app.include_router(invite.router)
app.include_router(otp.router)
app.include_router(user.router)
app.include_router(reflection.router)
app.include_router(reflection_history.router)

@app.get("/health", tags=["system"])
def health_check():
    return {"status": "healthy", "service": "Sarthi API", "version": "1.0.10"}

@app.get("/", tags=["system"])
def root():
    return {"message": "Welcome to Sarthi API"}