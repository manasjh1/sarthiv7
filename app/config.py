from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Existing SARTHI7 settings
    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Distress Detection settings
    openai_api_key: str
    pinecone_api_key: str
    pinecone_index: str
    pinecone_namespace: str = "distress"
    openai_embed_model: str = "text-embedding-3-large"
    pinecone_env: Optional[str] = None  
             
    # ZeptoMail setting 
    zeptomail_token: str
    zeptomail_from_domain: str = "noreply@sarthi.me"
    zeptomail_from_name: str = "Sarthi"


    # WhatsApp Business API settings
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_template_name: str = "authentication"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
settings = Settings()