# File: backend/app/api/endpoints/resume_tailor.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Any, Dict
import logging
import json
import os
import uuid
import tempfile

from app.db.database import get_db
from app.db import models
from app.schemas.resume_tailor import (
    ResumeTailorRequest, ResumeTailorResponse, ATSScoreRequest,
    ATSScoreResponse, SectionContent, ResumeSection,
    SectionOptimizationRequest, SectionOptimizationResponse,
    PDFOptimizeRequest, PDFOptimizeResponse, PDFSectionMapResponse,
)
from app.utils.ats_scorer import (
    calculate_match_score, get_keyword_match,
    generate_improvement_suggestions
)
from app.llm.resume_tailor import (
    extract_resume_sections, optimize_section
)
from app.services.pdf_format_preserver import (
    optimize_pdf, build_section_map
)
from app.core.supabase_auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/optimize", response_model=ResumeTailorResponse)
async def optimize_resume(
    request: ResumeTailorRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Optimize resume sections based on job description.
    """
    try:
        # Get user's resume
        if request.resume_id:
            resume = db.query(models.Resume).filter(
                models.Resume.id == request.resume_id,
                models.Resume.owner_id == current_user.id
            ).first()
            
            if not resume:
                raise HTTPException(status_code=404, detail=f"Resume with ID {request.resume_id} not found")
        else:
            # Get the active resume
            resume = db.query(models.Resume).filter(
                models.Resume.owner_id == current_user.id,
                models.Resume.is_active == True
            ).first()
            
            if not resume:
                # If no active resume, get the most recent one
                resume = db.query(models.Resume).filter(
                    models.Resume.owner_id == current_user.id
                ).order_by(models.Resume.created_at.desc()).first()
                
                if not resume:
                    raise HTTPException(status_code=404, detail="No resume profiles found. Please create a resume first.")
        
        # Get resume content
        resume_content = resume.content
        
        # Extract sections from resume
        resume_sections = await extract_resume_sections(resume_content)
        # Calculate original ATS score
        original_ats_score = await calculate_match_score(resume_content, request.job_description)
        
        # Optimize requested sections
        optimized_sections = {}
        
        for section_type in request.sections_to_optimize:
            original_content = resume_sections.get(section_type, "")
            
            if original_content:
                optimized_content = await optimize_section(
                    section_type, original_content, request.job_description
                )
                
                optimized_sections[section_type] = SectionContent(
                    original_content=original_content,
                    optimized_content=optimized_content
                )
        
        # Calculate optimized ATS score
        # Create a version of the resume with optimized sections
        optimized_resume_content = resume_content
        
        for section_type, section_content in optimized_sections.items():
            # Replace original section with optimized section
            original = section_content.original_content
            optimized = section_content.optimized_content
            
            if original in resume_content:
                optimized_resume_content = optimized_resume_content.replace(original, optimized)
        
        optimized_ats_score = await calculate_match_score(optimized_resume_content, request.job_description)
        
        # Create response
        response = ResumeTailorResponse(
            original_ats_score=original_ats_score,
            optimized_ats_score=optimized_ats_score,
            optimized_sections=optimized_sections
        )

        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error optimizing resume: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/score", response_model=ATSScoreResponse)
async def calculate_ats_score(
    request: ATSScoreRequest,
    current_user: models.User = Depends(get_current_user)
) -> Any:
    """
    Calculate ATS score for a resume against a job description.
    """
    try:
        # Calculate ATS score
        score = await calculate_match_score(request.resume_content, request.job_description)
        
        # Get keyword match details
        keyword_match = await get_keyword_match(request.resume_content, request.job_description)
        
        # Generate improvement suggestions
        suggestions = await generate_improvement_suggestions(keyword_match, request.job_description)
        
        # Create response
        response = ATSScoreResponse(
            score=score,
            breakdown=keyword_match.get("breakdown", {}),
            suggestions=suggestions
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error calculating ATS score: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize-section", response_model=SectionOptimizationResponse)
async def optimize_single_section(
    request: SectionOptimizationRequest,
    current_user: models.User = Depends(get_current_user)
) -> Any:
    """
    Optimize a single resume section.
    """
    try:
        optimized_content = await optimize_section(
            request.section_type, request.section_content, request.job_description
        )

        return SectionOptimizationResponse(optimized_content=optimized_content)

    except Exception as e:
        logger.error(f"Error optimizing section: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_resume_or_active(db: Session, user: models.User, resume_id: int = None):
    """Helper to resolve a resume by ID or get the active one."""
    if resume_id:
        resume = db.query(models.Resume).filter(
            models.Resume.id == resume_id,
            models.Resume.owner_id == user.id
        ).first()
        if not resume:
            logger.warning(f"Resume {resume_id} not found for user {user.id} (email={user.email})")
            raise HTTPException(status_code=404, detail="Resume not found")
        return resume

    resume = db.query(models.Resume).filter(
        models.Resume.owner_id == user.id,
        models.Resume.is_active == True
    ).first()
    if not resume:
        resume = db.query(models.Resume).filter(
            models.Resume.owner_id == user.id
        ).order_by(models.Resume.created_at.desc()).first()
    if not resume:
        total = db.query(models.Resume).count()
        logger.warning(f"No resume for user {user.id} (email={user.email}). Total resumes in DB: {total}")
        raise HTTPException(status_code=404, detail="No resume found. Upload one first.")
    return resume


@router.post("/section-map", response_model=PDFSectionMapResponse)
async def get_section_map(
    request: PDFOptimizeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Preview the section map of a resume PDF — shows what sections were detected
    and their character counts before optimizing.
    """
    from app.services.storage import is_local_path, download_to_tempfile, RESUMES_BUCKET

    try:
        resume = _get_resume_or_active(db, current_user, request.resume_id)

        if not resume.file_path:
            raise HTTPException(
                status_code=400,
                detail="Original PDF not found. Re-upload the resume to enable format preservation."
            )

        if is_local_path(resume.file_path):
            if not os.path.exists(resume.file_path):
                raise HTTPException(status_code=400, detail="Original PDF not found. Re-upload the resume.")
            section_map = build_section_map(resume.file_path)
        else:
            with download_to_tempfile(RESUMES_BUCKET, resume.file_path) as tmp_path:
                section_map = build_section_map(tmp_path)

        return section_map

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building section map: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize-pdf", response_model=PDFOptimizeResponse)
async def optimize_resume_pdf(
    request: PDFOptimizeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Optimize a resume PDF while preserving EXACT formatting.
    Returns a download_id to retrieve the output PDF.
    """
    from app.services.storage import (
        is_local_path, download_to_tempfile, upload_file,
        RESUMES_BUCKET, TAILORED_BUCKET,
    )
    import fitz

    try:
        resume = _get_resume_or_active(db, current_user, request.resume_id)

        if not resume.file_path:
            raise HTTPException(
                status_code=400,
                detail="Original PDF not found. Re-upload the resume to enable format preservation."
            )

        download_id = uuid.uuid4().hex

        # Calculate original ATS score
        original_score = await calculate_match_score(
            resume.content, request.job_description
        )

        diff_download_id = uuid.uuid4().hex

        # Helper to run optimization on a local input path
        async def _run_optimize(input_path: str):
            fd, out_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            try:
                result = await optimize_pdf(
                    pdf_path=input_path,
                    output_path=out_path,
                    job_description=request.job_description,
                    resume_content=resume.content,
                )
                # Read optimized text for ATS scoring
                doc = fitz.open(out_path)
                optimized_text = "".join(page.get_text() for page in doc)
                doc.close()
                # Upload tailored PDF to Supabase
                with open(out_path, "rb") as f:
                    output_bytes = f.read()
                tailored_path = f"{current_user.id}/{download_id}.pdf"
                await upload_file(TAILORED_BUCKET, tailored_path, output_bytes)

                # Generate diff PDF: tailored PDF with green highlights on changed text
                try:
                    diff_doc = fitz.open(stream=output_bytes, filetype="pdf")
                    green = fitz.utils.getColor("green")
                    for change in result.get("changes", []):
                        opt_text = change.get("optimized", "")
                        if not opt_text:
                            continue
                        # Search for fragments of the optimized text in the PDF
                        # Use first ~60 chars to find the region
                        search_text = opt_text[:60].strip()
                        if len(search_text) < 5:
                            continue
                        for page in diff_doc:
                            rects = page.search_for(search_text)
                            if rects:
                                for rect in rects:
                                    annot = page.add_highlight_annot(rect)
                                    annot.set_colors(stroke=green)
                                    annot.set_opacity(0.35)
                                    annot.update()
                                break  # found on this page, skip to next change
                    diff_bytes = diff_doc.tobytes()
                    diff_doc.close()
                    diff_path = f"{current_user.id}/{diff_download_id}.pdf"
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
                raise HTTPException(status_code=400, detail="Original PDF not found. Re-upload the resume.")
            result, optimized_text = await _run_optimize(resume.file_path)
        else:
            with download_to_tempfile(RESUMES_BUCKET, resume.file_path) as tmp_path:
                result, optimized_text = await _run_optimize(tmp_path)

        optimized_score = await calculate_match_score(
            optimized_text, request.job_description
        )

        return PDFOptimizeResponse(
            download_id=download_id,
            diff_download_id=diff_download_id,
            sections_found=result["sections_found"],
            sections_optimized=result["sections_optimized"],
            original_ats_score=original_score,
            optimized_ats_score=optimized_score,
            changes=result.get("changes", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error optimizing PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{download_id}")
async def download_tailored_pdf(
    download_id: str,
    current_user: models.User = Depends(get_current_user),
):
    """Download a previously optimized PDF via Supabase signed URL."""
    from app.services.storage import get_signed_url, TAILORED_BUCKET

    storage_path = f"{current_user.id}/{download_id}.pdf"
    try:
        signed_url = get_signed_url(TAILORED_BUCKET, storage_path, expires_in=300)
        return RedirectResponse(url=signed_url)
    except Exception:
        raise HTTPException(status_code=404, detail="Tailored PDF not found or expired")