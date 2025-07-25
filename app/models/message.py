# app/models/message.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class MessageRequest(BaseModel):
    message: str
    session_id: str
    platform: str = "api"
    user_id: Optional[str] = None
    system_prompt: Optional[str] = None

class MessageResponse(BaseModel):
    response: str
    session_id: str
    timestamp: datetime = datetime.now()
    success: bool = True

class SessionInfo(BaseModel):
    session_id: str
    message_count: int
    user_messages: int
    assistant_messages: int
    platforms: List[str]
    last_activity: Optional[str] = None
    ttl_seconds: Optional[int] = None
    exists: bool

class HealthResponse(BaseModel):
    status: str
    components: dict
    session_manager: dict