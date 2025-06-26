from pydantic import BaseModel
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