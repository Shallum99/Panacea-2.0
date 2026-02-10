"""
Application endpoints — create, list, update, approve, send email.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime, timezone
import logging
import json

from app.db.database import get_db
from app.db import models
from app.schemas.application import (
    ApplicationCreate,
    ApplicationUpdate,
    ApplicationResponse,
)
from app.core.supabase_auth import get_current_user
from app.llm.claude_client import ClaudeClient
from app.services.email_sender import send_application_email

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=ApplicationResponse)
async def create_application(
    request: ApplicationCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create an application: store the job description, generate a message, return the application.
    """
    try:
        # Resolve resume
        resume = None
        if request.resume_id:
            resume = (
                db.query(models.Resume)
                .filter(
                    models.Resume.id == request.resume_id,
                    models.Resume.owner_id == current_user.id,
                )
                .first()
            )
            if not resume:
                raise HTTPException(status_code=404, detail="Resume not found")
        else:
            resume = (
                db.query(models.Resume)
                .filter(
                    models.Resume.owner_id == current_user.id,
                    models.Resume.is_active == True,
                )
                .first()
            )
            if not resume:
                resume = (
                    db.query(models.Resume)
                    .filter(models.Resume.owner_id == current_user.id)
                    .order_by(models.Resume.created_at.desc())
                    .first()
                )
            if not resume:
                raise HTTPException(
                    status_code=404,
                    detail="No resume found. Upload a resume first.",
                )

        # Save job description
        job_desc = models.JobDescription(
            title=request.position_title or "Untitled",
            content=request.job_description,
            owner_id=current_user.id,
        )
        db.add(job_desc)
        db.flush()

        # Extract company info + generate message via Claude
        claude = ClaudeClient()
        company_info = await claude.extract_company_info(request.job_description)
        company_name = company_info.get("company_name", "Unknown")

        # Build prompt (reuse logic from messages.py)
        resume_content = resume.content or ""
        try:
            resume_info = json.loads(resume.extracted_info) if resume.extracted_info else {}
        except Exception:
            resume_info = {}

        message_type_info = {
            "linkedin_message": {
                "format": "LinkedIn Message",
                "length": "around 300 characters",
                "tone": "professional yet conversational",
                "structure": "brief introduction, interest in position, 1-2 key qualifications, call to action",
            },
            "linkedin_connection": {
                "format": "LinkedIn Connection Request",
                "length": "around 200 characters",
                "tone": "brief and professional",
                "structure": "very brief introduction, reason for connecting, 1 key qualification, polite closing",
            },
            "linkedin_inmail": {
                "format": "LinkedIn InMail",
                "length": "around 2000 characters",
                "tone": "professional and confident",
                "structure": "formal greeting, introduction, background summary, key qualifications, specific company interest, call to action",
            },
            "email_short": {
                "format": "Short Email",
                "length": "around 1000 characters",
                "tone": "professional and direct",
                "structure": "greeting, brief introduction, 2-3 key qualifications, interest in company, call to action",
            },
            "email_detailed": {
                "format": "Detailed Email",
                "length": "around 3000 characters",
                "tone": "formal and detailed",
                "structure": "formal greeting, full introduction, detailed background, achievements, qualifications aligned with job, company-specific interest, closing with call to action",
            },
            "ycombinator": {
                "format": "Y Combinator Application",
                "length": "around 500 characters",
                "tone": "direct, innovative, and impactful",
                "structure": "concise intro, highlight of innovative abilities, entrepreneurial mindset, growth metrics if applicable, direct closing",
            },
        }

        msg_type = request.message_type
        if msg_type not in message_type_info:
            msg_type = "email_detailed"
        type_details = message_type_info[msg_type]

        recruiter_greeting = ""
        if request.recruiter_name:
            recruiter_greeting = f"Hi {request.recruiter_name},"

        system_prompt = (
            "You are an expert job application assistant. Craft personalized, "
            "professional outreach messages from job seekers to recruiters or hiring managers."
        )

        user_prompt = f"""
Create a personalized {type_details['format']} from a job seeker to a recruiter based on:

1. RESUME CONTENT:
{resume_content}

2. PROFILE TYPE: {resume.profile_type}
Primary languages: {resume.primary_languages}
Frameworks: {resume.frameworks}
Experience level: {resume.seniority} with {resume.years_experience}

3. JOB DESCRIPTION:
{request.job_description}

4. COMPANY INFO:
{json.dumps(company_info, indent=2)}

5. MESSAGE TYPE DETAILS:
Format: {type_details['format']}
Length: {type_details['length']}
Tone: {type_details['tone']}
Structure: {type_details['structure']}

{f"6. RECRUITER NAME: {request.recruiter_name}" if request.recruiter_name else "Hiring Team"}

Requirements:
- If recruiter name is provided, address them directly
- Include applicant's name and contact information
- Keep the message appropriate for {type_details['format']} with {type_details['length']}
- Highlight the most relevant skills that match the job
- Reference specific company information
- Include a clear call to action
- DO NOT use generic phrases like "I am writing to express my interest"
- Emphasize the candidate's experience as a {resume.profile_type}
{f"- Start the message with '{recruiter_greeting}'" if request.recruiter_name else ""}

Return ONLY the message text without any additional explanation or context.
"""

        generated_message = await claude._send_request(system_prompt, user_prompt)

        # Determine method
        method = models.ApplicationMethod.EMAIL.value if request.recipient_email else models.ApplicationMethod.MANUAL.value

        # Store company info on job description
        job_desc.company_info = json.dumps(company_info)
        db.flush()

        # Create application
        application = models.Application(
            owner_id=current_user.id,
            resume_id=resume.id,
            job_description_id=job_desc.id,
            status=models.ApplicationStatus.MESSAGE_GENERATED.value,
            method=method,
            company_name=company_name,
            position_title=request.position_title,
            recipient_email=request.recipient_email,
            job_url=request.job_url,
            message_type=request.message_type,
            generated_message=generated_message,
            final_message=generated_message,
        )
        db.add(application)
        db.commit()
        db.refresh(application)

        return application

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating application: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[ApplicationResponse])
async def list_applications(
    status: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all applications for the current user, optionally filtered by status."""
    query = db.query(models.Application).filter(
        models.Application.owner_id == current_user.id
    )
    if status:
        query = query.filter(models.Application.status == status)
    applications = query.order_by(desc(models.Application.created_at)).all()
    return applications


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single application."""
    app = (
        db.query(models.Application)
        .filter(
            models.Application.id == application_id,
            models.Application.owner_id == current_user.id,
        )
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: int,
    update: ApplicationUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an application (edit message, change recipient, etc.)."""
    app = (
        db.query(models.Application)
        .filter(
            models.Application.id == application_id,
            models.Application.owner_id == current_user.id,
        )
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if update.edited_message is not None:
        app.edited_message = update.edited_message
        app.final_message = update.edited_message
    if update.recipient_email is not None:
        app.recipient_email = update.recipient_email
    if update.recipient_name is not None:
        app.recipient_name = update.recipient_name
    if update.status is not None:
        app.status = update.status

    db.commit()
    db.refresh(app)
    return app


@router.post("/{application_id}/approve", response_model=ApplicationResponse)
async def approve_application(
    application_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark application as approved (ready to send)."""
    app = (
        db.query(models.Application)
        .filter(
            models.Application.id == application_id,
            models.Application.owner_id == current_user.id,
        )
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    app.status = models.ApplicationStatus.APPROVED.value
    db.commit()
    db.refresh(app)
    return app


@router.post("/{application_id}/send", response_model=ApplicationResponse)
async def send_application(
    application_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send the application email via SendGrid."""
    app = (
        db.query(models.Application)
        .filter(
            models.Application.id == application_id,
            models.Application.owner_id == current_user.id,
        )
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if not app.recipient_email:
        raise HTTPException(
            status_code=400, detail="Recipient email is required to send"
        )

    if app.status not in (
        models.ApplicationStatus.APPROVED.value,
        models.ApplicationStatus.MESSAGE_GENERATED.value,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send application in status '{app.status}'",
        )

    app.status = models.ApplicationStatus.SENDING.value
    db.commit()

    # Build subject line
    subject = f"Application for {app.position_title}" if app.position_title else "Job Application"

    # Get resume PDF if available
    resume_pdf_bytes = None
    resume_filename = None
    if app.resume_id:
        resume = db.query(models.Resume).filter(models.Resume.id == app.resume_id).first()
        if resume and resume.file_path:
            import os
            if os.path.exists(resume.file_path):
                with open(resume.file_path, "rb") as f:
                    resume_pdf_bytes = f.read()
                resume_filename = f"{resume.title or 'resume'}.pdf"

    # Get sender info from resume
    from_name = None
    from_email = None
    if app.resume_id:
        resume = db.query(models.Resume).filter(models.Resume.id == app.resume_id).first()
        if resume:
            from_name = resume.name or current_user.email.split("@")[0]

    try:
        message_id = await send_application_email(
            to_email=app.recipient_email,
            subject=subject,
            body=app.final_message or app.generated_message,
            from_name=from_name,
            resume_pdf_bytes=resume_pdf_bytes,
            resume_filename=resume_filename,
        )

        if message_id:
            app.status = models.ApplicationStatus.SENT.value
            app.email_message_id = message_id
            app.sent_at = datetime.now(timezone.utc)
            app.method = models.ApplicationMethod.EMAIL.value
        else:
            app.status = models.ApplicationStatus.FAILED.value

        db.commit()
        db.refresh(app)
        return app

    except Exception as e:
        logger.error(f"Failed to send application {application_id}: {e}")
        app.status = models.ApplicationStatus.FAILED.value
        db.commit()
        db.refresh(app)
        raise HTTPException(status_code=500, detail=f"Email sending failed: {e}")


@router.delete("/{application_id}")
async def delete_application(
    application_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an application."""
    app = (
        db.query(models.Application)
        .filter(
            models.Application.id == application_id,
            models.Application.owner_id == current_user.id,
        )
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    db.delete(app)
    db.commit()
    return {"detail": "Application deleted"}
