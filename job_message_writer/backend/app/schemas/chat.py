from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class ChatMessageCreate(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatConversationCreate(BaseModel):
    title: Optional[str] = "New Chat"
    context: Optional[Dict[str, Any]] = None


class ChatConversationResponse(BaseModel):
    id: int
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatConversationDetail(ChatConversationResponse):
    messages: List[ChatMessageResponse] = []
