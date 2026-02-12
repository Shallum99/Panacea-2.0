from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ProfileUpdate(BaseModel):
    """PATCH payload — only non-None fields are written."""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    professional_summary: Optional[str] = None
    master_skills: Optional[List[str]] = None
    target_roles: Optional[List[str]] = None
    target_industries: Optional[List[str]] = None
    target_locations: Optional[List[str]] = None
    work_arrangement: Optional[str] = None
    salary_range_min: Optional[int] = None
    salary_range_max: Optional[int] = None
    tone_formality: Optional[str] = None
    tone_confidence: Optional[str] = None
    tone_verbosity: Optional[str] = None


class ProfileResponse(BaseModel):
    # Personal
    full_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    # Professional
    professional_summary: Optional[str] = None
    # Skills
    master_skills: Optional[List[str]] = None
    # Preferences
    target_roles: Optional[List[str]] = None
    target_industries: Optional[List[str]] = None
    target_locations: Optional[List[str]] = None
    work_arrangement: Optional[str] = None
    salary_range_min: Optional[int] = None
    salary_range_max: Optional[int] = None
    # Tone
    tone_formality: str = "balanced"
    tone_confidence: str = "confident"
    tone_verbosity: str = "concise"


class WritingSampleCreate(BaseModel):
    title: Optional[str] = None
    content: str
    sample_type: Optional[str] = None


class WritingSampleResponse(BaseModel):
    id: int
    title: Optional[str] = None
    content: str
    sample_type: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
