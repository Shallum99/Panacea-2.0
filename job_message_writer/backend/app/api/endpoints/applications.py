"""
Application endpoints — create, list, update, approve, send email.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime, timezone
import asyncio
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


def build_message_prompts(
    resume_content: str,
    resume: models.Resume,
    job_description: str,
    message_type: str,
    recruiter_name: Optional[str],
) -> tuple:
    """Return (system_prompt, user_prompt, max_tokens) for message generation."""

    message_type_config = {
        "linkedin_message": {
            "format": "LinkedIn DM",
            "max_chars": "300 characters max",
            "style": "2-3 sentences. Punchy. One specific match to their role/company.",
            "max_tokens": 512,
        },
        "linkedin_connection": {
            "format": "LinkedIn connection note",
            "max_chars": "200 characters max",
            "style": "1-2 sentences. Ultra-concise. One hook.",
            "max_tokens": 256,
        },
        "linkedin_inmail": {
            "format": "LinkedIn InMail",
            "max_chars": "~1500 characters",
            "style": "3-4 short paragraphs. Lead with relevance, not introduction.",
            "max_tokens": 1536,
        },
        "email_short": {
            "format": "cold email",
            "max_chars": "~800 characters",
            "style": "Contact header, 2 short paragraphs mapping experience to role, one-line closer.",
            "max_tokens": 1024,
        },
        "email_detailed": {
            "format": "cold email",
            "max_chars": "~2000 characters",
            "style": "Contact header line, 3-4 paragraphs: (1) strongest match to JD, (2) quantified impact, (3) company-specific closer. No fluff.",
            "max_tokens": 2048,
        },
        "ycombinator": {
            "format": "YC startup application / cold email",
            "max_chars": "~500 characters",
            "style": "Contact header, 2-3 dense paragraphs with metrics. Ship fast, move fast energy.",
            "max_tokens": 512,
        },
    }

    config = message_type_config.get(message_type, message_type_config["email_detailed"])

    resume_name = resume.name or ""
    resume_email = resume.email or ""
    resume_phone = resume.phone or ""

    system_prompt = """You ghostwrite cold emails and messages for job seekers. You write exactly like a real human typing in Gmail — not like a language model.

VOICE:
- Vary your sentence structure. Mix short punchy sentences with longer ones. Real people don't write in uniform paragraph blocks.
- NEVER start 3+ sentences with "I" or "At [Company]" — vary your openings. Use "The", "That", "Built", "Shipped", the company name, a question, whatever.
- Don't list technologies in parentheses like "(React, Node, AWS, Docker)" — weave them naturally into what you built.
- Don't explain what a technology is. The reader knows.
- Use contractions. "I've" not "I have". "Didn't" not "did not".
- Em dashes over semicolons. Fragments are fine. This is an email, not an essay.

CONTENT:
- Pick 2-3 things from the resume that genuinely match what the JD asks for. Quality over quantity.
- For each, say WHAT you built and the RESULT (number/metric). One sentence, not a paragraph.
- Reference something specific about the company's actual product, problem, or industry — not generic "your mission resonates with me" garbage.
- End with a real sign-off: "Best," or "Cheers," followed by the person's first name. Like a real email.

WHAT MAKES IT SOUND LIKE AI (avoid all of these):
- Template structure where every paragraph follows the same "At [Company], I [verb] [thing] that [metric]" pattern
- Forced casual phrases like "Down to chat" or "Happy to hop on a call"
- Buzzwords: "passionate", "thrilled", "eager", "deep expertise", "well-positioned", "aligns perfectly", "leverage", "spearheaded"
- Opening with "I" as the very first word
- The phrase "I am writing to" or "I came across" or "I was excited to see"
- Praising the company generically ("Your commitment to innovation")
- Any sentence where you could replace the company name with any other company and it still works"""

    greeting = ""
    if recruiter_name:
        greeting = f"\n- Open with: Hi {recruiter_name},"
    else:
        greeting = "\n- No greeting — start directly with the body"

    user_prompt = f"""Write a {config['format']} for this job application.

Output format — return EXACTLY this structure:
Subject: [a short, specific email subject line — not "Application for [Role]", make it stand out]

[message body here]

CONSTRAINTS:
- {config['max_chars']}
- Style: {config['style']}{greeting}

RESUME:
{resume_content}

JOB DESCRIPTION:
{job_description}

RULES:
1. Read the JD. Find 2-3 requirements this person actually matches. Ignore the rest.
2. For each match, one sentence: what they built + the result. Don't pad it.
3. Last paragraph: reference something SPECIFIC about this company's product/challenge/industry. Then a one-line ask to connect.
4. Sign off with "Best," or "Cheers," and the person's first name.
5. The subject line should reference the specific role or company — not generic "Job Application".
6. Keep it SHORT. Recruiters skim. Every sentence must earn its place.

Output the subject line and message body ONLY. Nothing else."""

    return system_prompt, user_prompt, config["max_tokens"]


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

        # Build prompt and generate message via Claude
        claude = ClaudeClient()
        resume_content = resume.content or ""
        try:
            resume_info = json.loads(resume.extracted_info) if resume.extracted_info else {}
        except Exception:
            resume_info = {}

        msg_type = request.message_type or "email_detailed"
        system_prompt, user_prompt, msg_max_tokens = build_message_prompts(
            resume_content=resume_content,
            resume=resume,
            job_description=request.job_description,
            message_type=msg_type,
            recruiter_name=request.recruiter_name,
        )

        # Run company info extraction and message generation in parallel
        company_info, generated_message = await asyncio.gather(
            claude.extract_company_info(request.job_description),
            claude._send_request(system_prompt, user_prompt, max_tokens=msg_max_tokens),
        )
        company_name = company_info.get("company_name", "Unknown")

        # Determine method
        method = models.ApplicationMethod.EMAIL.value if request.recipient_email else models.ApplicationMethod.MANUAL.value

        # Store company info on job description
        job_desc.company_info = json.dumps(company_info)
        db.flush()

        # Parse subject from message if present
        subject = None
        body = generated_message
        if generated_message.startswith("Subject:"):
            parts = generated_message.split("\n\n", 1)
            subject = parts[0].replace("Subject:", "").strip()
            body = parts[1] if len(parts) > 1 else generated_message
        if not subject:
            subject = f"Application for {request.position_title}" if request.position_title else "Job Application"

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
            subject=subject,
            generated_message=body,
            final_message=body,
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


@router.post("/stream")
async def stream_application(
    request: ApplicationCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Stream message generation via SSE. Same logic as create_application but
    streams tokens as they're generated instead of waiting for the full response.
    """
    # Resolve resume (same as create_application)
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

    # Save job description (commit now so it's available inside the stream generator)
    job_desc = models.JobDescription(
        title=request.position_title or "Untitled",
        content=request.job_description,
        owner_id=current_user.id,
    )
    db.add(job_desc)
    db.commit()
    db.refresh(job_desc)

    # Build prompt
    claude = ClaudeClient()
    resume_content = resume.content or ""

    msg_type = request.message_type or "email_detailed"
    system_prompt, user_prompt, msg_max_tokens = build_message_prompts(
        resume_content=resume_content,
        resume=resume,
        job_description=request.job_description,
        message_type=msg_type,
        recruiter_name=request.recruiter_name,
    )

    # Capture variables needed inside the generator
    user_id = current_user.id
    resume_id = resume.id
    job_desc_id = job_desc.id

    async def event_stream():
        # Start company_info extraction in parallel (Haiku, fast)
        company_info_task = asyncio.create_task(
            claude.extract_company_info(request.job_description)
        )

        # Stream message tokens
        full_message = ""
        try:
            async for chunk in claude._stream_request(
                system_prompt, user_prompt, max_tokens=msg_max_tokens
            ):
                full_message += chunk
                yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"
            return

        # Get company info (should be done by now)
        company_info = await company_info_task
        company_name = company_info.get("company_name", "Unknown")

        # Save to DB using a fresh session (original Depends session may be closed)
        from app.db.database import SessionLocal
        save_db = SessionLocal()
        try:
            method = models.ApplicationMethod.EMAIL.value if request.recipient_email else models.ApplicationMethod.MANUAL.value
            job_desc_record = save_db.query(models.JobDescription).get(job_desc_id)
            if job_desc_record:
                job_desc_record.company_info = json.dumps(company_info)
                save_db.flush()

            # Parse subject from message if present (format: "Subject: ...\n\n...")
            subject = None
            body = full_message
            if full_message.startswith("Subject:"):
                parts = full_message.split("\n\n", 1)
                subject = parts[0].replace("Subject:", "").strip()
                body = parts[1] if len(parts) > 1 else full_message
            if not subject:
                subject = f"Application for {request.position_title}" if request.position_title else "Job Application"

            application = models.Application(
                owner_id=user_id,
                resume_id=resume_id,
                job_description_id=job_desc_id,
                status=models.ApplicationStatus.MESSAGE_GENERATED.value,
                method=method,
                company_name=company_name,
                position_title=request.position_title,
                recipient_email=request.recipient_email,
                job_url=request.job_url,
                message_type=request.message_type,
                subject=subject,
                generated_message=body,
                final_message=body,
            )
            save_db.add(application)
            save_db.commit()
            save_db.refresh(application)

            app_data = {
                "id": application.id,
                "status": application.status,
                "method": application.method,
                "company_name": application.company_name,
                "position_title": application.position_title,
                "recipient_email": application.recipient_email,
                "message_type": application.message_type,
                "subject": application.subject,
                "generated_message": application.generated_message,
                "final_message": application.final_message,
                "resume_id": application.resume_id,
                "job_description_id": application.job_description_id,
                "created_at": str(application.created_at) if application.created_at else None,
            }
            yield f"data: {json.dumps({'type': 'done', 'application': app_data})}\n\n"
        except Exception as e:
            logger.error(f"Error saving streamed application: {e}")
            save_db.rollback()
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"
        finally:
            save_db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
    if update.subject is not None:
        app.subject = update.subject
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

    if not current_user.gmail_refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Gmail not connected. Go to Settings and click 'Connect Gmail' to send emails from your account.",
        )

    app.status = models.ApplicationStatus.SENDING.value
    db.commit()

    # Use stored subject or fall back to default
    subject = app.subject or (f"Application for {app.position_title}" if app.position_title else "Job Application")

    # Get resume PDF if available
    from app.services.storage import is_local_path, download_file, RESUMES_BUCKET
    import os
    resume_pdf_bytes = None
    resume_filename = None
    if app.resume_id:
        resume = db.query(models.Resume).filter(models.Resume.id == app.resume_id).first()
        if resume and resume.file_path:
            if is_local_path(resume.file_path):
                if os.path.exists(resume.file_path):
                    with open(resume.file_path, "rb") as f:
                        resume_pdf_bytes = f.read()
            else:
                try:
                    resume_pdf_bytes = await download_file(RESUMES_BUCKET, resume.file_path)
                except Exception:
                    logger.warning("Failed to download resume for email attachment")
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
            from_email=current_user.email,
            resume_pdf_bytes=resume_pdf_bytes,
            resume_filename=resume_filename,
            gmail_refresh_token=current_user.gmail_refresh_token,
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
