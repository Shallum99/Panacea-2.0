"""
Chat agent tool definitions and execution dispatch.

Each tool maps to existing service code — no logic duplication.
Tool functions return (result_dict, rich_type) tuples.
"""

import json
import logging
import os
from typing import Any, Dict, Tuple, Optional
from sqlalchemy.orm import Session

from app.db import models
from app.core.rate_limit import _get_limit, _get_usage_count, log_usage, ADMIN_EMAILS

logger = logging.getLogger(__name__)


def _quota_error(action_type: str, used: int, limit: int) -> Dict[str, Any]:
    label = action_type.replace("_", " ")
    return {
        "error": "rate_limit_exceeded",
        "action": action_type,
        "used": used,
        "limit": limit,
        "message": f"You've used all {limit} {label}s. Upgrade your plan for more.",
    }


def _check_tool_quota(
    db: Session,
    user: models.User,
    action_type: str,
) -> Optional[Dict[str, Any]]:
    """Tool-level quota check for agentic flows that bypass FastAPI dependencies."""
    if os.environ.get("DEV_MODE", "").lower() == "true":
        return None

    # Admin bypass
    if user.email in ADMIN_EMAILS:
        return None

    limit = _get_limit(user, action_type)
    if limit is None:
        return None

    used = _get_usage_count(db, user.id, action_type)
    if used >= limit:
        logger.warning(
            f"Rate limit hit (tool): user {user.id} ({user.email}) "
            f"action={action_type} used={used} limit={limit}"
        )
        return _quota_error(action_type, used, limit)

    return None


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
        "name": "iterate_message",
        "description": "Modify an existing generated message based on user instructions (make shorter, more formal, add specific details, change tone, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "integer", "description": "ID of the application whose message to modify"},
                "instructions": {"type": "string", "description": "Instructions for how to modify the message (e.g. 'make it shorter', 'more formal tone', 'emphasize my Python experience')"},
            },
            "required": ["application_id", "instructions"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an application email to a recipient. Requires Gmail to be connected.",
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "integer", "description": "ID of the application to send"},
                "recipient_email": {"type": "string", "description": "Recipient email address (optional, uses application's recipient_email if omitted)"},
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
    {
        "name": "research_company",
        "description": "Research a company by scraping their website for info about mission, values, products, culture, and tech stack. Use this when the job description doesn't have enough company context to answer interview questions or generate highly personalized content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name (e.g. 'Stripe', 'Airbnb')"},
                "url": {"type": "string", "description": "Company website URL (optional — will be guessed from company name if not provided)"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "set_context",
        "description": "Extract and save key context from the conversation. Call this when the user shares a job description, URL, company name, recruiter name, or any application-relevant info. This updates the UI context panel so tools can use it automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_description": {"type": "string", "description": "Full job description text"},
                "position_title": {"type": "string", "description": "Job title extracted from JD"},
                "recruiter_name": {"type": "string", "description": "Recruiter/hiring manager name if found"},
                "recipient_email": {"type": "string", "description": "Recruiter email address if found"},
                "company_name": {"type": "string", "description": "Company name"},
                "job_url": {"type": "string", "description": "Job listing URL"},
            },
        },
    },
    {
        "name": "edit_tailored_resume",
        "description": "Make targeted text edits to a previously tailored resume PDF. Use when the user wants to change specific bullets, skills, sections, header text (name, contact info, LinkedIn URL), or any other content after tailoring. Takes the download_id of the current version and edit instructions, returns a new version.",
        "input_schema": {
            "type": "object",
            "properties": {
                "download_id": {"type": "string", "description": "download_id of the current tailored resume version"},
                "instructions": {"type": "string", "description": "What to change (e.g. 'change the second bullet in Experience to emphasize Python and add Kubernetes')"},
                "resume_id": {"type": "integer", "description": "Original resume ID (pass through from the tailor result for original PDF access)"},
            },
            "required": ["download_id", "instructions"],
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
        "iterate_message": _tool_iterate_message,
        "tailor_resume": _tool_tailor_resume,
        "get_ats_score": _tool_get_ats_score,
        "send_email": _tool_send_email,
        "list_applications": _tool_list_applications,
        "save_job": _tool_save_job,
        "research_company": _tool_research_company,
        "set_context": _tool_set_context,
        "edit_tailored_resume": _tool_edit_tailored_resume,
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


async def _tool_iterate_message(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    from app.llm.claude_client import ClaudeClient

    app_id = args["application_id"]
    instructions = args["instructions"]

    app = db.query(models.Application).filter(
        models.Application.id == app_id, models.Application.owner_id == user.id
    ).first()

    if not app:
        return {"error": "Application not found."}, "error"

    current_body = app.final_message or app.generated_message
    if not current_body:
        return {"error": "No message to iterate on."}, "error"

    claude = ClaudeClient()
    revised = await claude._send_request(
        system_prompt="You are a professional writing assistant. Revise the message according to the instructions. Return ONLY the revised message text, nothing else.",
        user_prompt=f"Original message:\n\n{current_body}\n\nInstructions: {instructions}",
        max_tokens=4096,
    )

    # Update the application
    app.final_message = revised.strip()
    db.commit()

    return {
        "application_id": app.id,
        "subject": app.subject,
        "message": app.final_message,
        "message_type": app.message_type,
    }, "message_preview"


async def _tool_tailor_resume(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    import os
    import uuid
    import tempfile
    import difflib
    import fitz
    from app.services.pdf_format_preserver import optimize_pdf
    from app.services.storage import (
        is_local_path, download_to_tempfile, upload_file,
        RESUMES_BUCKET, TAILORED_BUCKET,
    )
    from app.utils.ats_scorer import calculate_match_score

    jd = args["job_description"]
    resume_id = args.get("resume_id")
    quota_err = _check_tool_quota(db, user, "resume_tailor")
    if quota_err:
        return quota_err, "error"

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

    download_id = uuid.uuid4().hex
    diff_download_id = uuid.uuid4().hex

    # Calculate original ATS score
    original_score = await calculate_match_score(
        resume.content or "", jd
    )

    async def _run_optimize(input_path: str):
        fd, out_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            result = await optimize_pdf(
                pdf_path=input_path,
                output_path=out_path,
                job_description=jd,
                resume_content=resume.content or "",
            )
            # Read optimized text for ATS scoring
            doc = fitz.open(out_path)
            optimized_text = "".join(page.get_text() for page in doc)
            doc.close()

            # Compute font coverage from input PDF
            try:
                src_doc = fitz.open(input_path)
                total_fonts = 0
                fonts_with_enc = 0
                for pg in src_doc:
                    for fi in pg.get_fonts(full=True):
                        total_fonts += 1
                        if fi[3]:
                            fonts_with_enc += 1
                src_doc.close()
                result["font_coverage_pct"] = round(fonts_with_enc / total_fonts * 100, 1) if total_fonts else 100.0
            except Exception:
                result["font_coverage_pct"] = 100.0
            # Upload tailored PDF to storage
            with open(out_path, "rb") as f:
                output_bytes = f.read()
            tailored_path = f"{user.id}/{download_id}.pdf"
            await upload_file(TAILORED_BUCKET, tailored_path, output_bytes)

            # Generate diff PDF with green highlights on changed words
            try:
                orig_doc = fitz.open(input_path)
                diff_doc = fitz.open(stream=output_bytes, filetype="pdf")
                green = fitz.utils.getColor("green")

                def _group_words_by_line(words, y_tolerance=3):
                    lines = {}
                    for w in words:
                        y_key = round(w[1] / y_tolerance) * y_tolerance
                        if y_key not in lines:
                            lines[y_key] = []
                        lines[y_key].append(w)
                    for y_key in lines:
                        lines[y_key].sort(key=lambda w: w[0])
                    return lines

                for page_idx in range(min(len(diff_doc), len(orig_doc))):
                    orig_page = orig_doc[page_idx]
                    diff_page = diff_doc[page_idx]
                    orig_words = orig_page.get_text("words")
                    opt_words = diff_page.get_text("words")
                    orig_lines = _group_words_by_line(orig_words)
                    opt_lines = _group_words_by_line(opt_words)
                    orig_y_keys = sorted(orig_lines.keys())

                    for y_key, opt_line_words in opt_lines.items():
                        closest_y = min(orig_y_keys, key=lambda oy: abs(oy - y_key)) if orig_y_keys else None
                        if closest_y is None or abs(closest_y - y_key) > 6:
                            for w in opt_line_words:
                                rect = fitz.Rect(w[0], w[1], w[2], w[3])
                                annot = diff_page.add_highlight_annot(rect)
                                annot.set_colors(stroke=green)
                                annot.set_opacity(0.35)
                                annot.update()
                            continue
                        orig_line_words = orig_lines[closest_y]
                        orig_texts = [w[4] for w in orig_line_words]
                        opt_texts = [w[4] for w in opt_line_words]
                        if orig_texts == opt_texts:
                            continue
                        matcher = difflib.SequenceMatcher(None, orig_texts, opt_texts)
                        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
                            if tag in ("replace", "insert"):
                                for wi in range(j1, j2):
                                    w = opt_line_words[wi]
                                    rect = fitz.Rect(w[0], w[1], w[2], w[3])
                                    annot = diff_page.add_highlight_annot(rect)
                                    annot.set_colors(stroke=green)
                                    annot.set_opacity(0.35)
                                    annot.update()

                orig_doc.close()
                diff_bytes = diff_doc.tobytes()
                diff_doc.close()
                diff_path = f"{user.id}/{diff_download_id}.pdf"
                await upload_file(TAILORED_BUCKET, diff_path, diff_bytes)
            except Exception as e:
                logger.warning(f"Failed to generate diff PDF: {e}")

            return result, optimized_text
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass

    if is_local_path(resume.file_path):
        if not os.path.exists(resume.file_path):
            return {"error": "Original PDF not found. Re-upload the resume."}, "error"
        result, optimized_text = await _run_optimize(resume.file_path)
    else:
        with download_to_tempfile(RESUMES_BUCKET, resume.file_path) as tmp_path:
            result, optimized_text = await _run_optimize(tmp_path)

    optimized_score = await calculate_match_score(optimized_text, jd)
    log_usage(db, user.id, "resume_tailor")

    return {
        "resume_id": resume.id,
        "resume_title": resume.title,
        "download_id": download_id,
        "diff_download_id": diff_download_id,
        "sections_optimized": result.get("sections_optimized", []),
        "changes": result.get("changes", []),
        "ats_score_before": original_score,
        "ats_score_after": optimized_score,
        "font_coverage_pct": result.get("font_coverage_pct", 100.0),
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
    recipient_email = args.get("recipient_email")

    app = db.query(models.Application).filter(
        models.Application.id == app_id, models.Application.owner_id == user.id
    ).first()

    if not app:
        return {"error": "Application not found."}, "error"

    # Update recipient if provided
    if recipient_email:
        app.recipient_email = recipient_email
        db.commit()

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


async def _tool_research_company(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    """Scrape a company website and extract structured info via Claude."""
    import httpx
    from bs4 import BeautifulSoup
    from app.llm.claude_client import ClaudeClient

    company_name = args["company_name"]
    provided_url = args.get("url")

    # Build candidate URLs — strip everything except alphanumeric and hyphens
    import re as _re
    slug = _re.sub(r'[^a-z0-9-]', '', company_name.lower().replace(" ", ""))
    candidates = []
    if provided_url:
        candidates.append(provided_url)
    candidates.extend([
        f"https://www.{slug}.com",
        f"https://{slug}.com",
        f"https://{slug}.io",
    ])

    # Try to scrape main page + about page
    scraped_text = ""
    successful_url = None

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=15.0,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    ) as client:
        # Try each candidate URL
        for url in candidates:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    successful_url = url
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
                        tag.decompose()
                    main = soup.find("main") or soup.find("article") or soup.body or soup
                    text = main.get_text(separator="\n", strip=True)
                    scraped_text += f"--- MAIN PAGE ({url}) ---\n{text[:5000]}\n\n"
                    break
            except Exception:
                continue

        # Try /about page if we found the base URL
        if successful_url:
            base = successful_url.rstrip("/")
            for about_path in ["/about", "/about-us", "/company"]:
                try:
                    resp = await client.get(base + about_path)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
                            tag.decompose()
                        main = soup.find("main") or soup.find("article") or soup.body or soup
                        text = main.get_text(separator="\n", strip=True)
                        scraped_text += f"--- ABOUT PAGE ({base + about_path}) ---\n{text[:5000]}\n\n"
                        break
                except Exception:
                    continue

    if not scraped_text:
        return {
            "company_name": company_name,
            "error": f"Could not access {company_name}'s website. Try providing the URL directly.",
        }, "company_research"

    # Send to Claude for structured extraction
    claude = ClaudeClient()
    extraction_prompt = f"""Extract key company information from these web pages for {company_name}.

{scraped_text[:8000]}

Return a JSON object with these fields (use null for anything you can't determine):
{{
  "company_name": "Official name",
  "summary": "1-2 sentence description of what the company does",
  "mission": "Their mission or vision statement",
  "products": ["List of main products/services"],
  "tech_stack": ["Known technologies they use"],
  "culture_values": ["Core values or culture highlights"],
  "industry": "Primary industry",
  "size": "Company size if mentioned (e.g. '500+ employees')",
  "headquarters": "Location",
  "notable_facts": ["2-3 interesting facts useful for interview prep"]
}}

Return ONLY the JSON object, no extra text."""

    try:
        extraction_text = await claude._send_request(
            system_prompt="You extract structured company information from web content. Return only valid JSON.",
            user_prompt=extraction_prompt,
            max_tokens=2048,
            model=claude.fast_model,
        )

        import re
        match = re.search(r'\{[\s\S]*\}', extraction_text)
        if match:
            company_data = json.loads(match.group())
        else:
            company_data = json.loads(extraction_text)

        company_data["company_name"] = company_data.get("company_name", company_name)
        company_data["source_url"] = successful_url
        return company_data, "company_research"

    except Exception as e:
        logger.error(f"Company research extraction failed: {e}")
        return {
            "company_name": company_name,
            "raw_text": scraped_text[:3000],
            "note": "Extracted raw text but structured analysis failed.",
        }, "company_research"


async def _tool_set_context(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    """Pass-through tool — returns extracted context for the frontend to merge into state."""
    context = {k: v for k, v in args.items() if v}
    return context, "context_update"


async def _tool_edit_tailored_resume(args: Dict, user: models.User, db: Session) -> Tuple[Dict, str]:
    """Make targeted text edits to a previously tailored resume PDF.
    Supports bullets, skills, title skills, AND header text (name, contact info)."""
    import os
    import re
    import uuid
    import shutil
    import tempfile
    import difflib
    import fitz
    from app.services.pdf_format_preserver import (
        extract_spans_from_pdf,
        group_into_visual_lines,
        classify_lines,
        group_bullet_points,
        sanitize_bullet_replacements,
        apply_changes_to_pdf,
        LineType,
    )
    from app.services.storage import download_file, upload_file, TAILORED_BUCKET
    from app.llm.claude_client import ClaudeClient

    download_id = args["download_id"]
    instructions = args["instructions"]
    quota_err = _check_tool_quota(db, user, "resume_tailor")
    if quota_err:
        return quota_err, "error"

    # 1. Download the current tailored PDF from Supabase
    storage_path = f"{user.id}/{download_id}.pdf"
    try:
        pdf_bytes = await download_file(TAILORED_BUCKET, storage_path)
    except Exception:
        return {"error": "Could not find that tailored resume. The download_id may be wrong or expired."}, "error"

    # 2. Write to temp file for processing
    fd, input_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        with open(input_path, "wb") as f:
            f.write(pdf_bytes)

        # 3. Extract and classify text
        spans = extract_spans_from_pdf(input_path)
        visual_lines = group_into_visual_lines(spans)
        classified, _ = classify_lines(visual_lines)
        bullets, skills, title_skills = group_bullet_points(classified)

        # 3b. Extract header texts (name, contact info, etc.)
        # Include ALL structure lines — section headers like "EXPERIENCE" are
        # included too, but Claude's prompt says to only change what the user asks for.
        _SECTION_LABELS = {
            "experience", "education", "skills", "projects", "work experience",
            "professional experience", "technical skills", "certifications",
            "summary", "objective", "awards", "publications", "references",
            "volunteer", "interests", "activities", "leadership", "languages",
            "core competencies", "professional summary", "additional",
        }
        header_texts = []
        for cl in classified:
            if cl.line_type != LineType.STRUCTURE:
                continue
            clean = "".join(s.text for s in cl.spans).replace("\u200b", "").strip()
            if not clean or len(clean) < 2:
                continue
            # Skip obvious section headers like "EXPERIENCE", "EDUCATION"
            if clean.strip().lower() in _SECTION_LABELS:
                continue
            header_texts.append(clean)

        # 4. Build resume map for Claude — includes headers
        resume_map_parts = []

        for i, ht in enumerate(header_texts):
            resume_map_parts.append(f'HEADER {i}: "{ht}"')

        for i, bp in enumerate(bullets):
            section = bp.section_name or "Unknown"
            text = bp.full_text
            line_count = len(bp.text_lines)
            char_counts = bp.line_char_counts
            resume_map_parts.append(
                f"BULLET {i} [{section}] ({line_count} lines, chars per line: {char_counts}):\n  \"{text}\""
            )

        for i, sl in enumerate(skills):
            label_text = "".join(s.text for s in sl.label_spans).strip()
            content_text = "".join(s.text for s in sl.content_spans).strip()
            section = sl.section_name or "Skills"
            resume_map_parts.append(
                f"SKILL {i} [{section}]: \"{label_text}{content_text}\""
            )

        for i, tsl in enumerate(title_skills):
            resume_map_parts.append(
                f"TITLE_SKILL {i}: \"{tsl.full_text}\" (title: \"{tsl.title_part}\", skills: \"{tsl.skills_part}\")"
            )

        resume_map = "\n".join(resume_map_parts)

        # 5. Send to Claude for targeted edits
        claude = ClaudeClient()
        edit_prompt = f"""You are editing a resume PDF. Below is the current content organized by type.

The user wants to make this change:
{instructions}

CURRENT RESUME CONTENT:
{resume_map}

RULES:
- Only change what the user asked for. Leave everything else untouched.
- For HEADER fields: you CAN change names, contact info, LinkedIn URLs, etc. Return a single replacement string.
- For bullets: each replacement MUST have the SAME number of lines as the original.
- For bullets: each line should be SIMILAR length to the original line (some variation is OK, the PDF engine handles width).
- NEVER include bullet point characters (•, ●, ◦, ■, ▪, -, –, —) at the start of replacement text. The PDF already has the bullet marker. Return only the text content.
- For skills: return only the content part (not the bold label).
- For title skills: return only the skills part (not the title itself).
- Preserve all metrics, dates, company names unless the user explicitly asked to change them.

Return a JSON object with ONLY the items you changed:
{{
  "header_replacements": {{"<header_index>": "new header text"}},
  "bullet_replacements": {{"<bullet_index>": ["line 1 text", "line 2 text", ...]}},
  "skill_replacements": {{"<skill_index>": "new content without label"}},
  "title_replacements": {{"<title_index>": "new skills part"}}
}}

Return ONLY the JSON. If nothing should change, return {{"header_replacements": {{}}, "bullet_replacements": {{}}, "skill_replacements": {{}}, "title_replacements": {{}}}}"""

        edit_text = await claude._send_request(
            system_prompt="You make precise, targeted edits to resume text. Return only valid JSON.",
            user_prompt=edit_prompt,
            max_tokens=4096,
        )

        match = re.search(r'\{[\s\S]*\}', edit_text)
        if match:
            edits = json.loads(match.group())
        else:
            edits = json.loads(edit_text)

        # Parse header replacements: {index: new_text} → {orig_text: new_text}
        header_replacements = {}
        for k, v in edits.get("header_replacements", {}).items():
            idx = int(k)
            new_text = str(v).strip()
            if 0 <= idx < len(header_texts) and new_text:
                header_replacements[header_texts[idx]] = new_text

        bullet_replacements = {int(k): v for k, v in edits.get("bullet_replacements", {}).items()}
        skill_replacements = {
            int(k): str(v).strip()
            for k, v in edits.get("skill_replacements", {}).items()
            if str(v).strip()
        }
        title_replacements = {
            int(k): str(v).strip()
            for k, v in edits.get("title_replacements", {}).items()
            if str(v).strip()
        }

        # Sanitize with relaxed tolerance — Tc character spacing handles width
        bullet_replacements = sanitize_bullet_replacements(
            bullets, bullet_replacements, length_tolerance=0.50
        )
        skill_replacements = {
            idx: content for idx, content in skill_replacements.items()
            if 0 <= idx < len(skills)
        }
        title_replacements = {
            idx: content for idx, content in title_replacements.items()
            if 0 <= idx < len(title_skills)
        }

        has_body_changes = bool(bullet_replacements) or bool(skill_replacements) or bool(title_replacements)
        has_header_changes = bool(header_replacements)

        if not has_body_changes and not has_header_changes:
            return {"error": "No valid edits could be applied while preserving layout constraints."}, "error"

        # 6. Apply ALL changes to PDF via unified pipeline (including headers)
        fd2, output_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd2)
        try:
            apply_changes_to_pdf(
                input_path, output_path,
                bullets, skills,
                bullet_replacements, skill_replacements,
                title_skills, title_replacements,
                header_replacements=header_replacements if has_header_changes else None,
            )

            # Read output
            with open(output_path, "rb") as f:
                output_bytes = f.read()

            # 7. Upload new version
            new_download_id = uuid.uuid4().hex
            new_storage_path = f"{user.id}/{new_download_id}.pdf"
            await upload_file(TAILORED_BUCKET, new_storage_path, output_bytes)

            # 8. Generate diff PDF (previous vs new)
            diff_download_id = uuid.uuid4().hex
            try:
                prev_doc = fitz.open(input_path)
                new_doc = fitz.open(stream=output_bytes, filetype="pdf")
                green = fitz.utils.getColor("green")

                def _group_words_by_line(words, y_tolerance=3):
                    lines = {}
                    for w in words:
                        y_key = round(w[1] / y_tolerance) * y_tolerance
                        if y_key not in lines:
                            lines[y_key] = []
                        lines[y_key].append(w)
                    for y_key in lines:
                        lines[y_key].sort(key=lambda w: w[0])
                    return lines

                for page_idx in range(min(len(new_doc), len(prev_doc))):
                    prev_page = prev_doc[page_idx]
                    new_page = new_doc[page_idx]
                    prev_words = prev_page.get_text("words")
                    new_words = new_page.get_text("words")
                    prev_lines = _group_words_by_line(prev_words)
                    new_lines = _group_words_by_line(new_words)
                    prev_y_keys = sorted(prev_lines.keys())

                    for y_key, new_line_words in new_lines.items():
                        closest_y = min(prev_y_keys, key=lambda oy: abs(oy - y_key)) if prev_y_keys else None
                        if closest_y is None or abs(closest_y - y_key) > 6:
                            for w in new_line_words:
                                rect = fitz.Rect(w[0], w[1], w[2], w[3])
                                annot = new_page.add_highlight_annot(rect)
                                annot.set_colors(stroke=green)
                                annot.set_opacity(0.35)
                                annot.update()
                            continue
                        prev_line_words = prev_lines[closest_y]
                        prev_texts = [w[4] for w in prev_line_words]
                        new_texts = [w[4] for w in new_line_words]
                        if prev_texts == new_texts:
                            continue
                        matcher = difflib.SequenceMatcher(None, prev_texts, new_texts)
                        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
                            if tag in ("replace", "insert"):
                                for wi in range(j1, j2):
                                    w = new_line_words[wi]
                                    rect = fitz.Rect(w[0], w[1], w[2], w[3])
                                    annot = new_page.add_highlight_annot(rect)
                                    annot.set_colors(stroke=green)
                                    annot.set_opacity(0.35)
                                    annot.update()

                prev_doc.close()
                diff_bytes = new_doc.tobytes()
                new_doc.close()
                diff_path = f"{user.id}/{diff_download_id}.pdf"
                await upload_file(TAILORED_BUCKET, diff_path, diff_bytes)
            except Exception as e:
                logger.warning(f"Failed to generate edit diff PDF: {e}")

            # 9. Build changes list
            changes = []
            for orig_text, new_text in header_replacements.items():
                changes.append({
                    "section": "Header",
                    "type": "header",
                    "original": orig_text,
                    "optimized": new_text,
                })
            for idx, new_lines in bullet_replacements.items():
                if idx < len(bullets):
                    changes.append({
                        "section": bullets[idx].section_name,
                        "type": "bullet",
                        "original": bullets[idx].full_text,
                        "optimized": " ".join(new_lines),
                    })
            for idx, new_content in skill_replacements.items():
                if idx < len(skills):
                    label = "".join(s.text for s in skills[idx].label_spans).strip()
                    orig = "".join(s.text for s in skills[idx].content_spans).strip()
                    changes.append({
                        "section": skills[idx].section_name,
                        "type": "skill",
                        "original": f"{label}{orig}",
                        "optimized": f"{label}{new_content}",
                    })
            for idx, new_skills_part in title_replacements.items():
                if idx < len(title_skills):
                    ts = title_skills[idx]
                    changes.append({
                        "section": "Title",
                        "type": "title_skill",
                        "original": ts.full_text,
                        "optimized": f"{ts.title_part} ({new_skills_part})",
                    })

            log_usage(db, user.id, "resume_tailor")
            optimized_sections = sorted({
                c.get("section")
                for c in changes
                if c.get("section")
            })

            # Compute font coverage from input PDF
            try:
                cov_doc = fitz.open(input_path)
                _total = 0
                _with_enc = 0
                for pg in cov_doc:
                    for fi in pg.get_fonts(full=True):
                        _total += 1
                        if fi[3]:
                            _with_enc += 1
                cov_doc.close()
                _font_cov = round(_with_enc / _total * 100, 1) if _total else 100.0
            except Exception:
                _font_cov = 100.0

            result_data = {
                "resume_title": "Edited Resume",
                "download_id": new_download_id,
                "diff_download_id": diff_download_id,
                "sections_optimized": optimized_sections,
                "changes": changes,
                "font_coverage_pct": _font_cov,
            }
            # Pass through resume_id so the frontend can load the original PDF
            if args.get("resume_id"):
                result_data["resume_id"] = args["resume_id"]
            return result_data, "resume_tailored"

        finally:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass


def _apply_header_replacements_fitz(pdf_path: str, replacements: Dict[str, str]):
    """Apply header text replacements using PyMuPDF redaction with font matching."""
    import fitz
    import tempfile
    import shutil

    doc = fitz.open(pdf_path)
    modified = False

    for page in doc:
        for orig_text, new_text in replacements.items():
            rects = page.search_for(orig_text)
            if not rects:
                continue

            # Detect font info from the text location
            font_name = "helv"
            font_size = 12.0
            text_color = (0, 0, 0)

            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    line_text = "".join(s["text"] for s in line.get("spans", []))
                    if orig_text in line_text:
                        for span in line.get("spans", []):
                            if span["text"].strip() and any(
                                c in orig_text for c in span["text"].strip()[:5]
                            ):
                                font_name = span.get("font", "helv")
                                font_size = span.get("size", 12.0)
                                color_int = span.get("color", 0)
                                text_color = (
                                    ((color_int >> 16) & 0xFF) / 255.0,
                                    ((color_int >> 8) & 0xFF) / 255.0,
                                    (color_int & 0xFF) / 255.0,
                                )
                                break
                        break

            fitz_font = _map_to_fitz_font(font_name)
            for rect in rects:
                page.add_redact_annot(
                    rect,
                    text=new_text,
                    fontname=fitz_font,
                    fontsize=font_size,
                    text_color=text_color,
                    fill=(1, 1, 1),
                )

            page.apply_redactions()
            modified = True
            logger.info(f"[EDIT] Header replaced: '{orig_text}' → '{new_text}' (font={font_name}, size={font_size})")

    if modified:
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        import os as _os
        _os.close(fd)
        doc.save(tmp_path, garbage=4, deflate=True)
        doc.close()
        shutil.move(tmp_path, pdf_path)
    else:
        doc.close()


def _map_to_fitz_font(pdf_font_name: str) -> str:
    """Map PDF font name to a fitz built-in font name for redaction."""
    name = pdf_font_name.lower()
    if "times" in name:
        if "bold" in name and "italic" in name:
            return "tibi"
        if "bold" in name:
            return "tibo"
        if "italic" in name:
            return "tiit"
        return "tiro"
    if "arial" in name or "helvetica" in name:
        if "bold" in name and ("italic" in name or "oblique" in name):
            return "hebi"
        if "bold" in name:
            return "hebo"
        if "italic" in name or "oblique" in name:
            return "heit"
        return "helv"
    if "courier" in name:
        if "bold" in name and ("italic" in name or "oblique" in name):
            return "cobi"
        if "bold" in name:
            return "cobo"
        if "italic" in name or "oblique" in name:
            return "coit"
        return "cour"
    return "helv"
