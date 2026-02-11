from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class ApplicationCreate(BaseModel):
    job_description: str
    message_type: str = "email_detailed"
    resume_id: Optional[int] = None
    recruiter_name: Optional[str] = None
    recipient_email: Optional[str] = None
    job_url: Optional[str] = None
    position_title: Optional[str] = None


class ApplicationUpdate(BaseModel):
    edited_message: Optional[str] = None
    subject: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    status: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: int
    status: str
    method: str
    company_name: Optional[str] = None
    position_title: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    job_url: Optional[str] = None
    message_type: Optional[str] = None
    subject: Optional[str] = None
    generated_message: Optional[str] = None
    edited_message: Optional[str] = None
    final_message: Optional[str] = None
    resume_id: Optional[int] = None
    job_description_id: Optional[int] = None
    ats_score_before: Optional[float] = None
    ats_score_after: Optional[float] = None
    email_message_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
