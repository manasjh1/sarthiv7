from pydantic import BaseModel
from typing import Optional

class UniversalRequest(BaseModel):
    reflection_id: Optional[str] = None
    message: str

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