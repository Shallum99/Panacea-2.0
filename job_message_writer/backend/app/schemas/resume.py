# File: backend/app/schemas/resume.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ResumeBase(BaseModel):
    title: str  # Profile title (e.g., "My Frontend Resume")

class ResumeCreate(ResumeBase):
    # File is handled by Form in the API endpoint, not here
    pass

class ResumeInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: Optional[List[str]] = None
    years_experience: Optional[str] = None
    education: Optional[str] = None
    recent_job: Optional[str] = None
    recent_company: Optional[str] = None

class ProfileClassification(BaseModel):
    profile_type: Optional[str] = None  # Frontend, Backend, Full Stack, etc.
    primary_languages: Optional[List[str]] = None
    frameworks: Optional[List[str]] = None
    years_experience: Optional[str] = None
    seniority: Optional[str] = None
    industry_focus: Optional[str] = None

class ResumeResponse(BaseModel):
    id: int
    title: str
    filename: Optional[str] = None
    is_active: Optional[bool] = None
    extracted_info: Optional[ResumeInfo] = None
    profile_classification: Optional[ProfileClassification] = None
    
    class Config:
        orm_mode = True

class ResumeContentResponse(ResumeResponse):
    content: str  # The extracted text from the PDF