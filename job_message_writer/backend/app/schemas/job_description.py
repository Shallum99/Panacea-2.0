from pydantic import BaseModel
from typing import Optional, Dict, Any, List


class JobDescriptionBase(BaseModel):
    content: str
    title: Optional[str] = None


class JobDescriptionCreate(JobDescriptionBase):
    url: Optional[str] = None
    source: Optional[str] = None


class JobDescriptionResponse(JobDescriptionBase):
    id: int
    company_info: Optional[Dict[str, Any]] = None
    url: Optional[str] = None
    source: Optional[str] = None

    class Config:
        orm_mode = True


# URL extraction
class UrlExtractRequest(BaseModel):
    url: str


# Job board search
class JobSearchResult(BaseModel):
    id: str
    title: str
    company: str
    location: Optional[str] = None
    department: Optional[str] = None
    url: str
    source: str
    updated_at: Optional[str] = None
    workplace_type: Optional[str] = None
    salary_range: Optional[str] = None


class JobSearchResponse(BaseModel):
    results: List[JobSearchResult]
    total: int


class JobDetailResponse(BaseModel):
    id: str
    title: str
    company: str
    location: Optional[str] = None
    department: Optional[str] = None
    content: str
    url: str
    source: str
    apply_url: Optional[str] = None
    salary_range: Optional[str] = None
    workplace_type: Optional[str] = None
