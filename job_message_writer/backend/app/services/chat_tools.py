"""
Chat agent tool definitions and execution dispatch.

Each tool maps to existing service code — no logic duplication.
Tool functions return (result_dict, rich_type) tuples.
"""

import json
import logging
from typing import Any, Dict, Tuple, Optional
from sqlalchemy.orm import Session

from app.db import models

logger = logging.getLogger(__name__)


# ── Tool definitions (Claude API format) ──────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "search_jobs",
        "description": "Search for job listings on Greenhouse and Lever job boards. Use this when the user wants to find jobs by keyword, company, or location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search in job titles (e.g. 'backend engineer')"},
                "company": {"type": "string", "description": "Specific company slug (e.g. 'stripe', 'airbnb')"},
                "location": {"type": "string", "description": "Filter by location (e.g. 'San Francisco', 'Remote')"},
            },
        },
    },
    {
        "name": "get_job_detail",
        "description": "Get the full job description from a specific ATS listing. Use this after search_jobs to get the complete JD text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["greenhouse", "lever"], "description": "The ATS source"},
                "company": {"type": "string", "description": "Company slug"},
                "job_id": {"type": "string", "description": "The job ID from search results"},
            },
            "required": ["source", "company", "job_id"],
        },
    },
    {
        "name": "import_job_url",
        "description": "Extract a job description from any URL. Use when the user pastes a job listing link.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The job listing URL"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "list_resumes",
        "description": "List the user's uploaded resumes. Use this to see what resumes are available before generating messages or tailoring.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "generate_message",
        "description": "Generate a cover letter, email, or LinkedIn message for a job application. Requires job description text and optionally a resume ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_description": {"type": "string", "description": "The job description text"},
                "message_type": {
                    "type": "string",
                    "enum": ["email_short", "email_detailed", "linkedin_message", "linkedin_connection", "linkedin_inmail", "ycombinator"],
                    "description": "Type of message to generate",
                },
                "resume_id": {"type": "integer", "description": "ID of resume to use (optional, uses active resume if omitted)"},
                "recruiter_name": {"type": "string", "description": "Recruiter or hiring manager name if known"},
                "position_title": {"type": "string", "description": "The job title"},
            },
            "required": ["job_description"],
        },
    },
    {
        "name": "tailor_resume",
        "description": "Tailor a resume PDF to match a specific job description. Returns an ATS score and download link.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_description": {"type": "string", "description": "The job description text to tailor for"},
                "resume_id": {"type": "integer", "description": "ID of resume to tailor (optional, uses active resume if omitted)"},
            },
            "required": ["job_description"],
        },
    },
    {
        "name": "get_ats_score",
        "description": "Score a resume against a job description for ATS compatibility. Returns a score and improvement suggestions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_description": {"type": "string", "description": "The job description text"},
                "resume_id": {"type": "integer", "description": "ID of resume to score (optional, uses active resume if omitted)"},
            },
            "required": ["job_description"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an application email to a recipient. Requires Gmail to be connected.",
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "integer", "description": "ID of the application to send"},
            },
            "required": ["application_id"],
        },
    },
    {
        "name": "list_applications",
        "description": "List the user's job applications with their statuses. Use to check what's been applied to.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status (draft, message_generated, sent, etc.)"},
            },
        },
    },
    {
        "name": "save_job",
        "description": "Save a job description to the user's database for later use.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Job title"},
                "content": {"type": "string", "description": "Full job description text"},
                "company_name": {"type": "string", "description": "Company name"},
                "url": {"type": "string", "description": "URL of the job listing"},
                "source": {"type": "string", "description": "Source of the job (greenhouse, lever, url, manual)"},
            },
            "required": ["title", "content"],
        },
    },
]


# ── Tool dispatch ─────────────────────────────────────────────────────

async def execute_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    user: models.User,
    db: Session,
) -> Tuple[Dict[str, Any], str]:
    """
    Execute a tool and return (result_dict, rich_type).
    rich_type is a hint for frontend rendering.
    """
    handlers = {
        "search_jobs": _tool_search_jobs,
        "get_job_detail": _tool_get_job_detail,
        "import_job_url": _tool_import_job_url,
        "list_resumes": _tool_list_resumes,
        "generate_message": _tool_generate_message,
        "tailor_resume": _tool_tailor_resume,
        "get_ats_score": _tool_get_ats_score,
        "send_email": _tool_send_email,
        "list_applications": _tool_list_applications,
        "save_job": _tool_save_job,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}, "error"

    try:
        return await handler(tool_input, user, db)
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return {"error": str(e)}, "error"


# ── Tool implementations ─────────────────────────────────────────────

async def _tool_search_jobs(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    import httpx
    from app.api.endpoints.job_search import (
        _fetch_greenhouse_jobs, _fetch_lever_jobs,
        GREENHOUSE_COMPANIES, LEVER_COMPANIES,
    )

    q = args.get("query")
    company = args.get("company")
    location = args.get("location")

    companies_to_search = []
    if company:
        companies_to_search.append(("greenhouse", company))
        companies_to_search.append(("lever", company))
    else:
        for c in GREENHOUSE_COMPANIES[:10]:
            companies_to_search.append(("greenhouse", c))
        for c in LEVER_COMPANIES[:5]:
            companies_to_search.append(("lever", c))

    results = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for src, comp in companies_to_search:
            try:
                if src == "greenhouse":
                    jobs = await _fetch_greenhouse_jobs(client, comp, q, location)
                else:
                    jobs = await _fetch_lever_jobs(client, comp, q, location)
                results.extend([j.model_dump() for j in jobs])
            except Exception:
                continue

    results = results[:20]
    return {"jobs": results, "total": len(results)}, "job_cards"


async def _tool_get_job_detail(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    import httpx
    from app.api.endpoints.job_search import _fetch_greenhouse_detail, _fetch_lever_detail

    source = args["source"]
    company = args["company"]
    job_id = args["job_id"]

    async with httpx.AsyncClient(timeout=15.0) as client:
        if source == "greenhouse":
            detail = await _fetch_greenhouse_detail(client, company, job_id)
        else:
            detail = await _fetch_lever_detail(client, company, job_id)

    return detail.model_dump(), "job_detail"


async def _tool_import_job_url(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    from app.services.web_scraper import fetch_and_extract_jd

    url = args["url"]
    title, content, company_name = await fetch_and_extract_jd(url)

    return {
        "title": title,
        "content": content[:2000],
        "company": company_name,
        "full_content_length": len(content),
        "url": url,
    }, "job_detail"


async def _tool_list_resumes(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    resumes = (
        db.query(models.Resume)
        .filter(models.Resume.owner_id == user.id)
        .order_by(models.Resume.created_at.desc())
        .all()
    )

    resume_list = []
    for r in resumes:
        try:
            extracted = json.loads(r.extracted_info) if r.extracted_info else {}
        except Exception:
            extracted = {}

        resume_list.append({
            "id": r.id,
            "title": r.title,
            "is_active": r.is_active,
            "profile_type": r.profile_type,
            "seniority": r.seniority,
            "skills": extracted.get("skills", [])[:10],
        })

    return {"resumes": resume_list}, "resumes_list"


async def _tool_generate_message(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    from app.api.endpoints.applications import build_message_prompts
    from app.llm.claude_client import ClaudeClient

    jd = args["job_description"]
    msg_type = args.get("message_type", "email_detailed")
    resume_id = args.get("resume_id")
    recruiter_name = args.get("recruiter_name")
    position_title = args.get("position_title")

    # Resolve resume
    if resume_id:
        resume = db.query(models.Resume).filter(
            models.Resume.id == resume_id, models.Resume.owner_id == user.id
        ).first()
    else:
        resume = db.query(models.Resume).filter(
            models.Resume.owner_id == user.id, models.Resume.is_active == True
        ).first()
        if not resume:
            resume = db.query(models.Resume).filter(
                models.Resume.owner_id == user.id
            ).order_by(models.Resume.created_at.desc()).first()

    if not resume:
        return {"error": "No resume found. Upload a resume first."}, "error"

    writing_samples = (
        db.query(models.WritingSample)
        .filter(models.WritingSample.user_id == user.id)
        .order_by(models.WritingSample.created_at.desc())
        .limit(3)
        .all()
    )

    system_prompt, user_prompt, max_tokens = build_message_prompts(
        resume_content=resume.content or "",
        resume=resume,
        job_description=jd,
        message_type=msg_type,
        recruiter_name=recruiter_name,
        user=user,
        writing_samples=writing_samples,
    )

    claude = ClaudeClient()
    generated = await claude._send_request(system_prompt, user_prompt, max_tokens=max_tokens)

    # Parse subject if present
    subject = None
    body = generated
    if generated.startswith("Subject:"):
        parts = generated.split("\n\n", 1)
        subject = parts[0].replace("Subject:", "").strip()
        body = parts[1] if len(parts) > 1 else generated

    # Save as application
    jd_record = models.JobDescription(
        title=position_title or "Untitled",
        content=jd,
        owner_id=user.id,
    )
    db.add(jd_record)
    db.flush()

    app = models.Application(
        owner_id=user.id,
        resume_id=resume.id,
        job_description_id=jd_record.id,
        status=models.ApplicationStatus.MESSAGE_GENERATED.value,
        method=models.ApplicationMethod.MANUAL.value,
        company_name=position_title,
        position_title=position_title,
        message_type=msg_type,
        subject=subject or f"Application for {position_title or 'position'}",
        generated_message=body,
        final_message=body,
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    return {
        "application_id": app.id,
        "subject": app.subject,
        "message": body,
        "message_type": msg_type,
        "resume_used": resume.title,
    }, "message_preview"


async def _tool_tailor_resume(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    from app.services.pdf_format_preserver import tailor_resume

    jd = args["job_description"]
    resume_id = args.get("resume_id")

    if resume_id:
        resume = db.query(models.Resume).filter(
            models.Resume.id == resume_id, models.Resume.owner_id == user.id
        ).first()
    else:
        resume = db.query(models.Resume).filter(
            models.Resume.owner_id == user.id, models.Resume.is_active == True
        ).first()

    if not resume:
        return {"error": "No resume found."}, "error"
    if not resume.file_path:
        return {"error": "Resume has no PDF file."}, "error"

    result = await tailor_resume(resume.file_path, jd, user.id)

    return {
        "resume_title": resume.title,
        "download_id": result.get("download_id"),
        "sections_optimized": result.get("sections_optimized", []),
        "ats_score_before": result.get("ats_score_before"),
        "ats_score_after": result.get("ats_score_after"),
    }, "resume_tailored"


async def _tool_get_ats_score(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    from app.llm.claude_client import ClaudeClient

    jd = args["job_description"]
    resume_id = args.get("resume_id")

    if resume_id:
        resume = db.query(models.Resume).filter(
            models.Resume.id == resume_id, models.Resume.owner_id == user.id
        ).first()
    else:
        resume = db.query(models.Resume).filter(
            models.Resume.owner_id == user.id, models.Resume.is_active == True
        ).first()

    if not resume:
        return {"error": "No resume found."}, "error"

    claude = ClaudeClient()
    score_text = await claude._send_request(
        system_prompt="You are an ATS resume scoring expert. Score the resume against the job description. Return ONLY valid JSON.",
        user_prompt=f"""Score this resume against the job description on a 0-100 scale.

RESUME:
{(resume.content or '')[:3000]}

JOB DESCRIPTION:
{jd[:3000]}

Return JSON: {{"score": <number>, "strengths": [<list of 3 strengths>], "improvements": [<list of 3 improvements>], "missing_keywords": [<list of missing keywords>]}}""",
        max_tokens=1024,
        model=claude.fast_model,
    )

    try:
        import re
        match = re.search(r'\{[\s\S]*\}', score_text)
        if match:
            score_data = json.loads(match.group())
        else:
            score_data = json.loads(score_text)
    except Exception:
        score_data = {"score": 0, "error": "Failed to parse score"}

    score_data["resume_title"] = resume.title
    return score_data, "resume_score"


async def _tool_send_email(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    from app.services.email_sender import send_application_email

    app_id = args["application_id"]
    app = db.query(models.Application).filter(
        models.Application.id == app_id, models.Application.owner_id == user.id
    ).first()

    if not app:
        return {"error": "Application not found."}, "error"
    if not app.recipient_email:
        return {"error": "No recipient email set on this application."}, "error"
    if not user.gmail_refresh_token:
        return {"error": "Gmail not connected. Go to Settings to connect."}, "error"

    subject = app.subject or f"Application for {app.position_title or 'position'}"
    message_id = await send_application_email(
        to_email=app.recipient_email,
        subject=subject,
        body=app.final_message or app.generated_message,
        from_name=user.full_name or user.email.split("@")[0],
        from_email=user.email,
        gmail_refresh_token=user.gmail_refresh_token,
    )

    if message_id:
        from datetime import datetime, timezone
        app.status = models.ApplicationStatus.SENT.value
        app.email_message_id = message_id
        app.sent_at = datetime.now(timezone.utc)
        app.method = models.ApplicationMethod.EMAIL.value
        db.commit()
        return {
            "success": True,
            "recipient": app.recipient_email,
            "subject": subject,
        }, "email_sent"
    else:
        return {"error": "Failed to send email."}, "error"


async def _tool_list_applications(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    from sqlalchemy import desc

    query = db.query(models.Application).filter(
        models.Application.owner_id == user.id
    )
    status = args.get("status")
    if status:
        query = query.filter(models.Application.status == status)

    apps = query.order_by(desc(models.Application.created_at)).limit(20).all()

    app_list = []
    for a in apps:
        app_list.append({
            "id": a.id,
            "company_name": a.company_name,
            "position_title": a.position_title,
            "status": a.status,
            "method": a.method,
            "recipient_email": a.recipient_email,
            "sent_at": str(a.sent_at) if a.sent_at else None,
            "created_at": str(a.created_at) if a.created_at else None,
        })

    return {"applications": app_list, "total": len(app_list)}, "applications_list"


async def _tool_save_job(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    from app.llm.claude_client import ClaudeClient

    title = args["title"]
    content = args["content"]
    company_name = args.get("company_name")
    url = args.get("url")
    source = args.get("source", "manual")

    jd = models.JobDescription(
        title=title,
        content=content,
        owner_id=user.id,
        url=url,
        source=source,
    )
    db.add(jd)
    db.commit()
    db.refresh(jd)

    # Extract company info in background
    try:
        claude = ClaudeClient()
        company_info = await claude.extract_company_info(content)
        jd.company_info = json.dumps(company_info)
        db.commit()
        company_name = company_info.get("company_name", company_name)
    except Exception:
        pass

    return {
        "job_id": jd.id,
        "title": title,
        "company": company_name,
        "source": source,
    }, "job_saved"
