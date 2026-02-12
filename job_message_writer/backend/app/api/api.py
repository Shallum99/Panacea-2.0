# Update in backend/app/api/api.py
from fastapi import APIRouter

from app.api.endpoints import messages, resumes, job_descriptions, users, test, auth, resume_tailor, applications, auto_apply, admin, billing, profile, job_search, chat

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
api_router.include_router(job_descriptions.router, prefix="/job-descriptions", tags=["job-descriptions"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(applications.router, prefix="/applications", tags=["applications"])
api_router.include_router(auto_apply.router, prefix="/auto-apply", tags=["auto-apply"])
api_router.include_router(test.router, prefix="/test", tags=["test"])
api_router.include_router(resume_tailor.router, prefix="/resume-tailor", tags=["resume-tailor"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(job_search.router, prefix="/jobs", tags=["job-search"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])