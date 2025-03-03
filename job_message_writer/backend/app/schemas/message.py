# File: backend/app/schemas/message.py
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

class ProfileClassification(BaseModel):
    profile_type: Optional[str] = None
    primary_languages: Optional[List[str]] = None
    frameworks: Optional[List[str]] = None
    years_experience: Optional[str] = None
    seniority: Optional[str] = None
    industry_focus: Optional[str] = None

class MessageRequest(BaseModel):
    resume_id: Optional[int] = None  # Optional - if not provided, use active profile
    job_description: str
    message_type: str  # "linkedin", "inmail", "email", "ycombinator"
    recruiter_name: Optional[str] = None  # Optional recruiter name

class MessageResponse(BaseModel):
    message: str
    company_info: Dict[str, Any]
    resume_info: Optional[Dict[str, Any]] = None
    profile_classification: Optional[ProfileClassification] = None
    resume_id: int  # Which resume was used
    resume_title: str  # The title of the resume profile