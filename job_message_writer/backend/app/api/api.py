# File: backend/app/api/api.py
# File: backend/app/api/api.py
from fastapi import APIRouter

from app.api.endpoints import messages, resumes, job_descriptions, users, test

api_router = APIRouter(prefix="/api")
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
api_router.include_router(job_descriptions.router, prefix="/job-descriptions", tags=["job-descriptions"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(test.router, prefix="/test", tags=["test"])