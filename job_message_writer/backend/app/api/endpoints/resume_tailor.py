# File: backend/app/api/endpoints/resume_tailor.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict
import logging
import json

from app.db.database import get_db
from app.db import models
from app.schemas.resume_tailor import (
    ResumeTailorRequest, ResumeTailorResponse, ATSScoreRequest, 
    ATSScoreResponse, SectionContent, ResumeSection,
    SectionOptimizationRequest, SectionOptimizationResponse
)
from app.utils.ats_scorer import (
    calculate_match_score, get_keyword_match, 
    generate_improvement_suggestions
)
from app.llm.resume_tailor import (
    extract_resume_sections, optimize_section
)
from app.api.endpoints.auth import get_current_user

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