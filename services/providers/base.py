from abc import ABC, abstractmethod
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class SendResult:
    """Result class for sending operations"""
    success: bool
    message_id: str = None
    error: str = None

class MessageProvider(ABC):
    """Abstract base class for all messaging providers"""
    
    @abstractmethod
    def send(self, recipient: str, content: str, metadata: Dict[str, Any] = None) -> SendResult:
        """Send message to recipient"""
        pass
    
    @abstractmethod
    def validate_recipient(self, recipient: str) -> bool:
        """Validate recipient format"""
        pass