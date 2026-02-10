# File: backend/app/api/endpoints/job_descriptions.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict, List
import logging
import json

from app.db.database import get_db
from app.db import models
from app.schemas.job_description import JobDescriptionBase, JobDescriptionCreate, JobDescriptionResponse
from app.llm.claude_client import ClaudeClient
from app.core.supabase_auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/analyze", response_model=Dict[str, Any])
async def analyze_job_description(
    job_desc: JobDescriptionBase,
    db: Session = Depends(get_db)
) -> Any:
    """Extract company information from a job description using Claude."""
    try:
        claude_client = ClaudeClient()
        company_info = await claude_client.extract_company_info(job_desc.content)
        return company_info
    except Exception as e:
        logger.error(f"Error analyzing job description: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=JobDescriptionResponse)
async def create_job_description(
    job_desc: JobDescriptionCreate,
    current_user: models.User = Depends(get_current_user),  # Use authenticated user
    db: Session = Depends(get_db)
) -> Any:
    """Create a new job description with Claude analysis."""
    try:
        # Use authenticated user
        user = current_user
        
        # Extract company info using Claude
        claude_client = ClaudeClient()
        company_info = await claude_client.extract_company_info(job_desc.content)
        
        # Create new job description
        db_job_desc = models.JobDescription(
            title=job_desc.title or "Untitled Job Description",
            content=job_desc.content,
            company_info=json.dumps(company_info),  # Convert to JSON string for storage
            owner_id=user.id
        )
        
        db.add(db_job_desc)
        db.commit()
        db.refresh(db_job_desc)
        
        # Return response
        return {
            "id": db_job_desc.id,
            "title": db_job_desc.title,
            "content": db_job_desc.content,
            "company_info": company_info
        }
    except Exception as e:
        logger.error(f"Error creating job description: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[JobDescriptionResponse])
def read_job_descriptions(
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(get_current_user),  # Use authenticated user
    db: Session = Depends(get_db)
) -> Any:
    """Get all job descriptions."""
    try:
        # Use authenticated user
        user = current_user
        
        # Get job descriptions for this user
        job_descriptions = db.query(models.JobDescription).filter(
            models.JobDescription.owner_id == user.id
        ).offset(skip).limit(limit).all()
        
        # Convert the stored company_info string back to dict
        result = []
        for jd in job_descriptions:
            try:
                company_info = json.loads(jd.company_info) if jd.company_info else {}
            except:
                company_info = {}
                
            result.append({
                "id": jd.id,
                "title": jd.title,
                "content": jd.content,
                "company_info": company_info
            })
            
        return result
    except Exception as e:
        logger.error(f"Error reading job descriptions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{jd_id}", response_model=JobDescriptionResponse)
def read_job_description(
    jd_id: int,
    current_user: models.User = Depends(get_current_user),  # Use authenticated user
    db: Session = Depends(get_db)
) -> Any:
    """Get a specific job description by ID."""
    try:
        # Get the job description that belongs to the current user
        jd = db.query(models.JobDescription).filter(
            models.JobDescription.id == jd_id,
            models.JobDescription.owner_id == current_user.id
        ).first()
        
        if not jd:
            raise HTTPException(status_code=404, detail="Job description not found")
            
        try:
            company_info = json.loads(jd.company_info) if jd.company_info else {}
        except:
            company_info = {}
            
        return {
            "id": jd.id,
            "title": jd.title,
            "content": jd.content,
            "company_info": company_info
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading job description: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))