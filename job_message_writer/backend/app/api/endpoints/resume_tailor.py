# File: backend/app/api/endpoints/resume_tailor.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Any, Dict
import logging
import json
import os
import uuid

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
    try:
        resume = _get_resume_or_active(db, current_user, request.resume_id)

        if not resume.file_path or not os.path.exists(resume.file_path):
            logger.warning(f"PDF missing for resume {resume.id}: file_path={resume.file_path!r}, exists={os.path.exists(resume.file_path) if resume.file_path else 'N/A'}")
            raise HTTPException(
                status_code=400,
                detail="Original PDF not found. Re-upload the resume to enable format preservation."
            )

        section_map = build_section_map(resume.file_path)
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
    try:
        resume = _get_resume_or_active(db, current_user, request.resume_id)

        if not resume.file_path or not os.path.exists(resume.file_path):
            logger.warning(f"PDF missing for resume {resume.id}: file_path={resume.file_path!r}, exists={os.path.exists(resume.file_path) if resume.file_path else 'N/A'}")
            raise HTTPException(
                status_code=400,
                detail="Original PDF not found. Re-upload the resume to enable format preservation."
            )

        # Prepare output path
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "uploads", "tailored"
        )
        os.makedirs(output_dir, exist_ok=True)
        download_id = uuid.uuid4().hex
        output_path = os.path.join(output_dir, f"{download_id}.pdf")

        # Calculate original ATS score
        original_score = await calculate_match_score(
            resume.content, request.job_description
        )

        # Run format-preserving optimization
        result = await optimize_pdf(
            pdf_path=resume.file_path,
            output_path=output_path,
            job_description=request.job_description,
            resume_content=resume.content,
        )

        # Calculate optimized ATS score from the new PDF text
        import fitz
        doc = fitz.open(output_path)
        optimized_text = ""
        for page in doc:
            optimized_text += page.get_text()
        doc.close()

        optimized_score = await calculate_match_score(
            optimized_text, request.job_description
        )

        return PDFOptimizeResponse(
            download_id=download_id,
            sections_found=result["sections_found"],
            sections_optimized=result["sections_optimized"],
            original_ats_score=original_score,
            optimized_ats_score=optimized_score,
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
    """Download a previously optimized PDF."""
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "uploads", "tailored"
    )
    file_path = os.path.join(output_dir, f"{download_id}.pdf")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Tailored PDF not found or expired")

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"tailored_resume_{download_id[:8]}.pdf",
    )