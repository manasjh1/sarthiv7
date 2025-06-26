from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
from app.schemas import UniversalRequest, UniversalResponse
import uuid

class BaseStage(ABC):
    """Abstract base class for all stages"""
    
    def __init__(self, db: Session):
        self.db = db
    
    @abstractmethod
    def process(self, request: UniversalRequest, user_id: uuid.UUID) -> UniversalResponse:
        """Process the stage request and return response"""
        pass
    
    @abstractmethod
    def get_prompt(self) -> str:
        """Get the prompt message for this stage"""
        pass
    
    @abstractmethod
    def get_stage_number(self) -> int:
        """Get the stage number"""
        pass