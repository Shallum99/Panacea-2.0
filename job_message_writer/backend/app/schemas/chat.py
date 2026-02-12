from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ChatMessageCreate(BaseModel):
    message: str


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


class ChatConversationResponse(BaseModel):
    id: int
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatConversationDetail(ChatConversationResponse):
    messages: List[ChatMessageResponse] = []
