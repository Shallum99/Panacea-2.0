# File: backend/app/schemas/resume_tailor.py
from enum import Enum
from pydantic import BaseModel
from typing import Dict, List, Optional, Any


class ResumeSection(str, Enum):
    SKILLS = "SKILLS"
    PROJECTS = "PROJECTS"
    EXPERIENCE = "EXPERIENCE"


class SectionContent(BaseModel):
    original_content: str
    optimized_content: str


class ResumeTailorRequest(BaseModel):
    job_description: str
    resume_id: Optional[int] = None  # If not provided, use active resume
    sections_to_optimize: List[ResumeSection]


class ResumeTailorResponse(BaseModel):
    original_ats_score: float
    optimized_ats_score: float
    optimized_sections: Dict[ResumeSection, SectionContent]


class ATSScoreRequest(BaseModel):
    job_description: str
    resume_content: str


class ATSScoreResponse(BaseModel):
    score: float
    breakdown: Dict[str, float]
    suggestions: List[str]


class SectionOptimizationRequest(BaseModel):
    section_type: ResumeSection
    section_content: str
    job_description: str


class SectionOptimizationResponse(BaseModel):
    optimized_content: str