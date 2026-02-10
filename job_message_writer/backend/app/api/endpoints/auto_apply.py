"""
Auto-apply endpoints — email-based and URL-based (Playwright).
Includes WebSocket for real-time progress updates.
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.supabase_auth import get_current_user
from app.db import models
from app.db.database import get_db
from app.services.auto_apply.browser_worker import (
    ApplyTask,
    cancel_task,
    get_task,
    run_auto_apply,
    submit_application,
    SCREENSHOT_DIR,
)
from app.services.email_sender import send_application_email
from app.services.pdf_format_preserver import optimize_pdf
from app.utils.ats_scorer import calculate_match_score

router = APIRouter()
logger = logging.getLogger(__name__)


# --- Schemas ---

class EmailAutoApplyRequest(BaseModel):
    job_description: str
    recipient_email: str
    resume_id: Optional[int] = None
    position_title: Optional[str] = None
    recruiter_name: Optional[str] = None
    optimize_resume: bool = True  # Whether to tailor the resume first


class URLAutoApplyRequest(BaseModel):
    job_url: str
    resume_id: Optional[int] = None
    cover_letter: Optional[str] = None


class AutoApplyStatusResponse(BaseModel):
    task_id: str
    job_url: str
    status: str
    steps: List[Dict[str, Any]]
    error: Optional[str] = None


# --- Email Auto-Apply ---

@router.post("/email")
async def email_auto_apply(
    request: EmailAutoApplyRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Full email auto-apply flow:
    1. Optionally optimize the resume PDF for the job description
    2. Generate a tailored message
    3. Send email with resume attached
    """
    # Resolve resume
    resume = None
    if request.resume_id:
        resume = db.query(models.Resume).filter(
            models.Resume.id == request.resume_id,
            models.Resume.owner_id == current_user.id,
        ).first()
    else:
        resume = db.query(models.Resume).filter(
            models.Resume.owner_id == current_user.id,
            models.Resume.is_active == True,
        ).first()

    if not resume:
        raise HTTPException(status_code=404, detail="No resume found")

    # Step 1: Optionally optimize PDF
    tailored_pdf_path = None
    if request.optimize_resume and resume.file_path and os.path.exists(resume.file_path):
        try:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "uploads", "tailored"
            )
            os.makedirs(output_dir, exist_ok=True)
            tailored_pdf_path = os.path.join(output_dir, f"auto_{uuid.uuid4().hex}.pdf")

            await optimize_pdf(
                pdf_path=resume.file_path,
                output_path=tailored_pdf_path,
                job_description=request.job_description,
                resume_content=resume.content,
            )
        except Exception as e:
            logger.warning(f"PDF optimization failed, using original: {e}")
            tailored_pdf_path = None

    # Step 2: Generate message
    from app.llm.claude_client import ClaudeClient
    claude = ClaudeClient()

    company_info = await claude.extract_company_info(request.job_description)
    company_name = company_info.get("company_name", "Unknown")

    system_prompt = (
        "You are an expert job application assistant. Write a personalized, "
        "professional email from a job seeker to a recruiter."
    )
    user_prompt = f"""Write a professional job application email.

RESUME:
{resume.content[:3000]}

JOB DESCRIPTION:
{request.job_description[:3000]}

COMPANY: {company_name}
POSITION: {request.position_title or 'the role'}
{f"RECRUITER: {request.recruiter_name}" if request.recruiter_name else ""}

Requirements:
- Professional, concise email (200-400 words)
- Highlight 2-3 most relevant qualifications
- Reference the company specifically
- Include a clear call to action
- Mention that resume is attached

Return ONLY the email body text.
"""

    message = await claude._send_request(system_prompt, user_prompt)

    # Step 3: Send email
    pdf_path = tailored_pdf_path or resume.file_path
    resume_bytes = None
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            resume_bytes = f.read()

    subject = f"Application for {request.position_title}" if request.position_title else f"Application — {company_name}"

    message_id = await send_application_email(
        to_email=request.recipient_email,
        subject=subject,
        body=message,
        from_name=resume.name or current_user.email.split("@")[0],
        resume_pdf_bytes=resume_bytes,
        resume_filename=f"{resume.title or 'resume'}.pdf",
    )

    # Create application record
    job_desc = models.JobDescription(
        title=request.position_title or "Auto-Apply",
        content=request.job_description,
        company_info=json.dumps(company_info),
        owner_id=current_user.id,
    )
    db.add(job_desc)
    db.flush()

    from datetime import datetime, timezone as tz
    application = models.Application(
        owner_id=current_user.id,
        resume_id=resume.id,
        job_description_id=job_desc.id,
        status="sent" if message_id else "failed",
        method="email",
        company_name=company_name,
        position_title=request.position_title,
        recipient_email=request.recipient_email,
        message_type="email_detailed",
        generated_message=message,
        final_message=message,
        email_message_id=message_id,
        sent_at=datetime.now(tz.utc) if message_id else None,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    return {
        "status": "sent" if message_id else "failed",
        "application_id": application.id,
        "company_name": company_name,
        "message_preview": message[:200] + "...",
        "email_message_id": message_id,
        "resume_optimized": tailored_pdf_path is not None,
    }


# --- URL Auto-Apply ---

@router.post("/url", response_model=AutoApplyStatusResponse)
async def url_auto_apply(
    request: URLAutoApplyRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Start a URL-based auto-apply task.
    Returns a task_id for tracking progress via WebSocket or polling.
    """
    # Resolve resume
    resume = None
    if request.resume_id:
        resume = db.query(models.Resume).filter(
            models.Resume.id == request.resume_id,
            models.Resume.owner_id == current_user.id,
        ).first()
    else:
        resume = db.query(models.Resume).filter(
            models.Resume.owner_id == current_user.id,
            models.Resume.is_active == True,
        ).first()

    if not resume:
        raise HTTPException(status_code=404, detail="No resume found")

    # Build user info from resume
    user_info = {
        "name": resume.name or "",
        "email": resume.email or current_user.email,
        "phone": resume.phone or "",
        "current_title": resume.recent_job or "",
        "current_company": resume.recent_company or "",
    }

    task_id = uuid.uuid4().hex
    resume_path = resume.file_path if resume.file_path and os.path.exists(resume.file_path) else None

    # Run in background
    asyncio.create_task(
        run_auto_apply(
            task_id=task_id,
            job_url=request.job_url,
            user_info=user_info,
            resume_path=resume_path,
            cover_letter=request.cover_letter,
        )
    )

    # Return immediately with task_id
    return AutoApplyStatusResponse(
        task_id=task_id,
        job_url=request.job_url,
        status="running",
        steps=[{"name": "Starting...", "status": "running", "detail": "", "screenshot_path": None, "timestamp": None}],
    )


@router.get("/status/{task_id}", response_model=AutoApplyStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: models.User = Depends(get_current_user),
):
    """Poll the status of an auto-apply task."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return AutoApplyStatusResponse(**task.to_dict())


@router.post("/cancel/{task_id}")
async def cancel_auto_apply(
    task_id: str,
    current_user: models.User = Depends(get_current_user),
):
    """Cancel a running auto-apply task."""
    success = cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Task not found or already completed")
    return {"status": "cancelled"}


@router.post("/submit/{task_id}")
async def submit_auto_apply(
    task_id: str,
    current_user: models.User = Depends(get_current_user),
):
    """Confirm and submit the auto-filled application."""
    try:
        task = await submit_application(task_id)
        return AutoApplyStatusResponse(**task.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/screenshot/{filename}")
async def get_screenshot(
    filename: str,
    current_user: models.User = Depends(get_current_user),
):
    """Serve a screenshot image."""
    path = os.path.join(SCREENSHOT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path, media_type="image/png")


# --- WebSocket for real-time progress ---

@router.websocket("/ws/{task_id}")
async def auto_apply_ws(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time auto-apply progress."""
    await websocket.accept()

    try:
        # Poll the task and send updates
        last_step_count = 0
        while True:
            task = get_task(task_id)
            if not task:
                await websocket.send_json({"error": "Task not found"})
                break

            # Send update if there are new steps or status changed
            current_step_count = len(task.steps)
            if current_step_count != last_step_count or task.status in ("done", "failed", "cancelled", "review"):
                await websocket.send_json(task.to_dict())
                last_step_count = current_step_count

            if task.status in ("done", "failed", "cancelled", "review"):
                break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
