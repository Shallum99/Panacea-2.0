from pydantic import BaseModel
from typing import Optional, Dict, Any

class JobDescriptionBase(BaseModel):
    content: str
    title: Optional[str] = None

class JobDescriptionCreate(JobDescriptionBase):
    pass

class JobDescriptionResponse(JobDescriptionBase):
    id: int
    company_info: Optional[Dict[str, Any]] = None
    
    class Config:
        orm_mode = True